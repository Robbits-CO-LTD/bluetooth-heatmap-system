"""データ統合モジュール - スキャナーとデータベースを接続"""
import logging
import asyncio
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from src.database.connection import DatabaseConnection
from src.database.repositories import (
    DeviceRepository,
    TrajectoryRepository,
    DwellTimeRepository,
    FlowRepository,
    HeatmapRepository,
    DetectionRepository,
    AnalyticsRepository
)
from src.database.models import Device, TrajectoryPoint, Detection
from src.core.config_loader import load_config


class DataIntegration:
    """スキャンデータとデータベースを統合するクラス"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初期化
        
        Args:
            config: データベース設定
        """
        self.logger = logging.getLogger(__name__)
        
        # 設定読み込み
        if config is None:
            full_config = load_config()
            config = full_config.get('database', {})
        self.config = config
        
        # データベース接続
        self.db_connection = None
        self.is_connected = False
        
        # バッチ処理設定
        self.batch_size = config.get('batch_size', 100)
        self.flush_interval = config.get('flush_interval', 5.0)
        
        # バッファ
        self.device_buffer = []
        self.position_buffer = []
        self.detection_buffer = []
        self.trajectory_buffer = []
        self.dwell_buffer = []
        
        # 統計
        self.stats = {
            'devices_saved': 0,
            'positions_saved': 0,
            'detections_saved': 0,
            'db_errors': 0
        }
        
    async def connect(self) -> bool:
        """データベースに接続"""
        try:
            self.db_connection = DatabaseConnection(self.config)
            await self.db_connection.connect()
            self.is_connected = True
            self.logger.info("Database connected successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            self.is_connected = False
            return False
            
    async def disconnect(self):
        """データベース接続を切断"""
        if self.db_connection:
            # バッファをフラッシュ
            await self.flush_all_buffers()
            await self.db_connection.disconnect()
            self.is_connected = False
            self.logger.info("Database disconnected")
            
    @asynccontextmanager
    async def get_session(self):
        """データベースセッションを取得"""
        if not self.is_connected:
            raise RuntimeError("Database not connected")
        async with self.db_connection.get_session() as session:
            yield session
            
    async def save_device(self, device_id: str, mac_address: str, 
                          device_name: Optional[str] = None,
                          position: Optional[Tuple[float, float]] = None,
                          zone_id: Optional[str] = None,
                          rssi: Optional[float] = None) -> bool:
        """
        デバイス情報を保存
        
        Args:
            device_id: デバイスID（ハッシュ化済み）
            mac_address: MACアドレス（ハッシュ化済み）
            device_name: デバイス名
            position: 現在位置
            zone_id: 現在のゾーン
            rssi: 信号強度
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        try:
            async with self.get_session() as session:
                device_repo = DeviceRepository(session)
                
                # 既存デバイスを確認
                existing = await device_repo.get_by_id(device_id)
                
                if existing:
                    # 既存デバイスを更新
                    update_data = {
                        'last_seen': datetime.utcnow(),
                        'total_detections': existing.total_detections + 1
                    }
                    
                    if position:
                        update_data['current_x'] = position[0]
                        update_data['current_y'] = position[1]
                    if zone_id:
                        update_data['current_zone'] = zone_id
                    if rssi:
                        update_data['signal_strength'] = rssi
                        
                    await device_repo.update(device_id, update_data)
                else:
                    # 新規デバイスを作成
                    device_data = {
                        'device_id': device_id,
                        'mac_address': mac_address,
                        'device_name': device_name,
                        'device_type': 'unknown',
                        'first_seen': datetime.utcnow(),
                        'last_seen': datetime.utcnow(),
                        'current_x': position[0] if position else None,
                        'current_y': position[1] if position else None,
                        'current_zone': zone_id,
                        'signal_strength': rssi,
                        'total_detections': 1
                    }
                    await device_repo.create(device_data)
                
                self.stats['devices_saved'] += 1
                return True
                
        except Exception as e:
            self.logger.error(f"Error saving device {device_id}: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.stats['db_errors'] += 1
            return False
            
    async def save_position(self, device_id: str, position: Tuple[float, float],
                           zone_id: Optional[str] = None, confidence: float = 1.0,
                           timestamp: Optional[datetime] = None) -> bool:
        """
        位置情報を保存
        
        Args:
            device_id: デバイスID
            position: 位置座標
            zone_id: ゾーンID
            confidence: 信頼度
            timestamp: タイムスタンプ
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        position_data = {
            'device_id': device_id,
            'x': position[0],
            'y': position[1],
            'zone_id': zone_id,
            'confidence': confidence,
            'timestamp': timestamp or datetime.utcnow()
        }
        
        self.position_buffer.append(position_data)
        
        # バッファサイズを超えたらフラッシュ
        if len(self.position_buffer) >= self.batch_size:
            await self.flush_positions()
            
        return True
        
    async def save_detection(self, device_id: str, receiver_id: str,
                             rssi: float, distance: float,
                             timestamp: Optional[datetime] = None) -> bool:
        """
        検出情報を保存
        
        Args:
            device_id: デバイスID
            receiver_id: 受信機ID
            rssi: 信号強度
            distance: 推定距離
            timestamp: タイムスタンプ
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        detection_data = {
            'device_id': device_id,
            'receiver_id': receiver_id,
            'rssi': rssi,
            'distance': distance,
            'timestamp': timestamp or datetime.utcnow()
        }
        
        self.detection_buffer.append(detection_data)
        
        # バッファサイズを超えたらフラッシュ
        if len(self.detection_buffer) >= self.batch_size:
            await self.flush_detections()
            
        return True
        
    async def save_trajectory_point(self, trajectory_id: str, device_id: str,
                                   position: Tuple[float, float],
                                   zone_id: Optional[str] = None,
                                   timestamp: Optional[datetime] = None) -> bool:
        """
        軌跡ポイントを保存
        
        Args:
            trajectory_id: 軌跡ID
            device_id: デバイスID
            position: 位置座標
            zone_id: ゾーンID
            timestamp: タイムスタンプ
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        point_data = {
            'trajectory_id': trajectory_id,
            'device_id': device_id,
            'x': position[0],
            'y': position[1],
            'zone_id': zone_id,
            'timestamp': timestamp or datetime.utcnow()
        }
        
        self.trajectory_buffer.append(point_data)
        
        # バッファサイズを超えたらフラッシュ
        if len(self.trajectory_buffer) >= self.batch_size:
            await self.flush_trajectories()
            
        return True
        
    async def save_dwell_time(self, device_id: str, zone_id: str,
                              entry_time: datetime, exit_time: Optional[datetime] = None,
                              duration_seconds: Optional[float] = None) -> bool:
        """
        滞留時間を保存
        
        Args:
            device_id: デバイスID
            zone_id: ゾーンID
            entry_time: 入場時刻
            exit_time: 退場時刻
            duration_seconds: 滞留時間（秒）
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        try:
            async with self.get_session() as session:
                dwell_repo = DwellTimeRepository(session)
                
                dwell_data = {
                    'device_id': device_id,
                    'zone_id': zone_id,
                    'entry_time': entry_time,
                    'exit_time': exit_time,
                    'duration_seconds': duration_seconds,
                    'is_active': exit_time is None
                }
                
                await dwell_repo.create(dwell_data)
                return True
                
        except Exception as e:
            self.logger.error(f"Error saving dwell time: {e}")
            self.stats['db_errors'] += 1
            return False
            
    async def save_flow_transition(self, device_id: str, from_zone: str,
                                   to_zone: str, timestamp: datetime,
                                   duration: float) -> bool:
        """
        フロー遷移を保存
        
        Args:
            device_id: デバイスID
            from_zone: 元のゾーン
            to_zone: 移動先のゾーン
            timestamp: タイムスタンプ
            duration: 遷移時間
            
        Returns:
            保存成功したかどうか
        """
        if not self.is_connected:
            return False
            
        try:
            async with self.get_session() as session:
                flow_repo = FlowRepository(session)
                
                # フロー統計を更新
                await flow_repo.increment_flow(from_zone, to_zone, timestamp.date())
                return True
                
        except Exception as e:
            self.logger.error(f"Error saving flow transition: {e}")
            self.stats['db_errors'] += 1
            return False
            
    async def flush_positions(self):
        """位置バッファをフラッシュ"""
        if not self.position_buffer or not self.is_connected:
            return
            
        try:
            async with self.get_session() as session:
                trajectory_repo = TrajectoryRepository(session)
                
                # バッチ挿入
                for pos_data in self.position_buffer:
                    # 軌跡ポイントとして保存
                    point = TrajectoryPoint(
                        device_id=pos_data['device_id'],
                        x=pos_data['x'],
                        y=pos_data['y'],
                        zone_id=pos_data['zone_id'],
                        timestamp=pos_data['timestamp']
                    )
                    session.add(point)
                
                await session.commit()
                self.stats['positions_saved'] += len(self.position_buffer)
                self.position_buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Error flushing positions: {e}")
            self.stats['db_errors'] += 1
            
    async def flush_detections(self):
        """検出バッファをフラッシュ"""
        if not self.detection_buffer or not self.is_connected:
            return
            
        try:
            async with self.get_session() as session:
                # バッチ挿入
                for det_data in self.detection_buffer:
                    detection = Detection(**det_data)
                    session.add(detection)
                
                await session.commit()
                self.stats['detections_saved'] += len(self.detection_buffer)
                self.detection_buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Error flushing detections: {e}")
            self.stats['db_errors'] += 1
            
    async def flush_trajectories(self):
        """軌跡バッファをフラッシュ"""
        if not self.trajectory_buffer or not self.is_connected:
            return
            
        try:
            async with self.get_session() as session:
                trajectory_repo = TrajectoryRepository(session)
                
                # バッチ挿入
                await trajectory_repo.add_points(
                    self.trajectory_buffer[0]['trajectory_id'],
                    self.trajectory_buffer
                )
                
                self.trajectory_buffer.clear()
                
        except Exception as e:
            self.logger.error(f"Error flushing trajectories: {e}")
            self.stats['db_errors'] += 1
            
    async def flush_all_buffers(self):
        """すべてのバッファをフラッシュ"""
        await self.flush_positions()
        await self.flush_detections()
        await self.flush_trajectories()
        
    async def periodic_flush(self):
        """定期的にバッファをフラッシュ"""
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush_all_buffers()
            
    def get_statistics(self) -> Dict:
        """統計情報を取得"""
        return {
            'devices_saved': self.stats['devices_saved'],
            'positions_saved': self.stats['positions_saved'],
            'detections_saved': self.stats['detections_saved'],
            'db_errors': self.stats['db_errors'],
            'buffer_sizes': {
                'positions': len(self.position_buffer),
                'detections': len(self.detection_buffer),
                'trajectories': len(self.trajectory_buffer)
            },
            'is_connected': self.is_connected
        }