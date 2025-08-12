"""Bluetooth動線分析システム メインアプリケーション"""
import asyncio
import sys
import signal
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import numpy as np

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config_loader import ConfigLoader
from src.core.scanner import BluetoothScanner, MultiReceiverScanner
from src.core.device_manager import DeviceManager
from src.core.position_calculator import PositionCalculator, ReceiverMeasurement
from src.core.data_integration import DataIntegration
from src.analysis.trajectory_analyzer import TrajectoryAnalyzer
from src.analysis.dwell_time_analyzer import DwellTimeAnalyzer
from src.analysis.flow_analyzer import FlowAnalyzer


class MotionAnalysisSystem:
    """動線分析システムのメインクラス"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        初期化
        
        Args:
            config_path: 設定ファイルパス
        """
        # 設定読み込み
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.load()
        self.layout = self.config_loader.layout
        
        # ロガー設定
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # コンポーネント初期化
        self.scanner = None
        self.device_manager = None
        self.position_calculator = None
        self.trajectory_analyzer = None
        self.dwell_analyzer = None
        self.flow_analyzer = None
        self.data_integration = None  # データベース統合
        
        # システム状態
        self.is_running = False
        self._tasks = []
        
    def _setup_logging(self):
        """ロギング設定"""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # ログディレクトリ作成
        log_file = log_config.get('file', 'logs/motion_analysis.log')
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # ハンドラー設定
        handlers = [
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
        
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=handlers
        )
        
    async def initialize(self):
        """システム初期化"""
        self.logger.info("システムを初期化しています...")
        
        try:
            # データベース統合を初期化
            self.logger.info("データベース統合を初期化中...")
            self.data_integration = DataIntegration(self.config.get('database', {}))
            db_connected = await self.data_integration.connect()
            
            if db_connected:
                self.logger.info("[OK] データベース接続成功")
            else:
                self.logger.warning("[NG] データベース接続失敗 - メモリモードで動作します")
                self.logger.warning("データベース設定を確認してください: .env ファイル")
            
            # デバイスマネージャー
            self.device_manager = DeviceManager(self.config.get('device_management', {}))
            
            # 位置計算
            self.position_calculator = PositionCalculator(
                self.config.get('positioning', {}),
                self.layout
            )
            
            # 分析エンジン
            self.trajectory_analyzer = TrajectoryAnalyzer(
                self.config.get('analysis', {}).get('trajectory', {})
            )
            self.dwell_analyzer = DwellTimeAnalyzer(
                self.config.get('analysis', {}).get('dwell_time', {})
            )
            self.flow_analyzer = FlowAnalyzer(
                self.config.get('analysis', {}).get('flow', {}),
                self.layout
            )
            
            # スキャナー初期化
            scan_config = self.config.get('scanning', {})
            
            # 単一スキャナーモードを強制する場合
            use_single_scanner = scan_config.get('use_single_scanner', False)
            
            # 複数受信機の場合（ただし単一スキャナーモードが無効の場合のみ）
            if self.layout.get('receivers') and not use_single_scanner:
                self.scanner = MultiReceiverScanner(scan_config, self.layout['receivers'])
                self.logger.info(f"複数受信機モード: {len(self.layout['receivers'])}台の受信機")
            else:
                # 単一受信機
                self.scanner = BluetoothScanner(scan_config)
                self.logger.info("単一スキャナーモード")
                
            self.logger.info("初期化完了")
            
        except Exception as e:
            self.logger.error(f"初期化エラー: {e}")
            raise
            
    async def start(self):
        """システム開始"""
        if self.is_running:
            self.logger.warning("システムは既に実行中です")
            return
            
        self.is_running = True
        self.logger.info("動線分析システムを開始します")
        
        try:
            # スキャナー開始
            if isinstance(self.scanner, MultiReceiverScanner):
                await self.scanner.start_all()
            else:
                await self.scanner.start()
                
            # 並行タスクを起動
            self._tasks = [
                asyncio.create_task(self._scanning_loop()),
                asyncio.create_task(self._analysis_loop()),
                asyncio.create_task(self._maintenance_loop()),
                asyncio.create_task(self._reporting_loop())
            ]
            
            # データベース統合がある場合、定期フラッシュタスクを追加
            if self.data_integration and self.data_integration.is_connected:
                self._tasks.append(
                    asyncio.create_task(self.data_integration.periodic_flush())
                )
            
            # タスク実行
            await asyncio.gather(*self._tasks)
            
        except asyncio.CancelledError:
            self.logger.info("システムを停止しています...")
        except Exception as e:
            self.logger.error(f"実行エラー: {e}")
            raise
            
    async def stop(self):
        """システム停止"""
        self.is_running = False
        
        # タスクをキャンセル
        for task in self._tasks:
            task.cancel()
            
        # スキャナー停止
        if self.scanner:
            if isinstance(self.scanner, MultiReceiverScanner):
                await self.scanner.stop_all()
            else:
                await self.scanner.stop()
        
        # データベース接続を切断
        if self.data_integration:
            await self.data_integration.disconnect()
                
        self.logger.info("システムを停止しました")
        
    async def _scanning_loop(self):
        """スキャンループ"""
        scan_interval = self.config.get('scanning', {}).get('interval', 1.0)
        
        while self.is_running:
            try:
                # デバイス検出
                if isinstance(self.scanner, MultiReceiverScanner):
                    all_devices = self.scanner.get_all_devices()
                    await self._process_multi_receiver_data(all_devices)
                else:
                    devices = self.scanner.get_current_devices()
                    if devices:
                        self.logger.info(f"処理中: {len(devices)}個のデバイス")
                    await self._process_single_receiver_data(devices)
                    
                await asyncio.sleep(scan_interval)
                
            except Exception as e:
                self.logger.error(f"スキャンエラー: {e}")
                import traceback
                self.logger.error(f"トレースバック: {traceback.format_exc()}")
                await asyncio.sleep(5)
                
    async def _process_multi_receiver_data(self, all_devices: Dict):
        """
        複数受信機のデータを処理
        
        Args:
            all_devices: 受信機ID -> デバイスリストの辞書
        """
        # デバイスごとに測定値をグループ化
        device_measurements = {}
        
        for receiver_id, devices in all_devices.items():
            receiver_info = self.config_loader.get_receiver_by_id(receiver_id)
            if not receiver_info:
                continue
                
            receiver_pos = tuple(receiver_info['position'])
            
            for device in devices:
                mac = device.mac_address
                
                if mac not in device_measurements:
                    device_measurements[mac] = []
                    
                # 測定値を作成
                measurement = ReceiverMeasurement(
                    receiver_id=receiver_id,
                    receiver_position=receiver_pos,
                    rssi=device.rssi,
                    distance=self.position_calculator.rssi_to_distance(device.rssi),
                    timestamp=device.timestamp.timestamp()
                )
                
                device_measurements[mac].append(measurement)
                
        # 各デバイスの位置を計算
        for mac, measurements in device_measurements.items():
            # デバイス登録
            device_obj = self.device_manager.register_device(
                mac_address=mac,
                device_name=measurements[0].receiver_id  # 仮の名前
            )
            
            # 位置計算
            position = self.position_calculator.calculate_position(measurements)
            
            if position:
                # ゾーン判定
                zone_id = self.position_calculator.get_zone_id(position)
                
                # データベースにデバイスを保存
                if self.data_integration and self.data_integration.is_connected:
                    await self.data_integration.save_device(
                        device_id=device_obj.device_id,
                        mac_address=device_obj.mac_address,
                        device_name=device_obj.device_name,
                        position=position,
                        zone_id=zone_id,
                        rssi=measurements[0].rssi
                    )
                
                # 更新
                await self._update_device_position(
                    device_obj.device_id,
                    position,
                    zone_id
                )
                
    async def _process_single_receiver_data(self, devices: List):
        """
        単一受信機のデータを処理
        
        Args:
            devices: デバイスリスト
        """
        # デバイスの総数を取得して均等に配置
        num_devices = len(devices)
        
        for idx, device in enumerate(devices):
            # デバイス登録
            device_obj = self.device_manager.register_device(
                mac_address=device.mac_address,
                device_name=device.device_name,
                rssi=device.rssi
            )
            
            # 簡易的な位置推定（単一受信機では正確な位置は計算できない）
            # RSSIベースの距離推定のみ
            distance = self.position_calculator.rssi_to_distance(device.rssi)
            
            # 簡易的な位置を推定（受信機を中心とした円上の点）
            import hashlib
            import math
            # 受信機の位置を施設の中心と仮定
            facility_width = self.config.get('facility', {}).get('dimensions', {}).get('width', 20)
            facility_height = self.config.get('facility', {}).get('dimensions', {}).get('height', 15)
            receiver_x = facility_width / 2
            receiver_y = facility_height / 2
            
            # デバイスを円形に均等配置
            # MACアドレスのハッシュを使って一貫した位置を生成
            mac_hash = hashlib.md5(device.mac_address.encode()).hexdigest()
            # ハッシュ値から一意の角度を生成（0から2πの範囲）
            hash_value = int(mac_hash[:8], 16)
            # デバイスごとに異なる角度を確実に割り当て
            # 黄金角を使用してより良い分散を実現
            golden_angle = math.pi * (3.0 - math.sqrt(5.0))  # 約2.39996ラジアン
            angle = (hash_value * golden_angle) % (2 * math.pi)
            
            # RSSIの変動を考慮して位置に若干のランダム性を追加
            # 時間経過とともに位置が少し変化するようにタイムスタンプも考慮
            time_factor = (device.timestamp.timestamp() % 100) / 100.0
            angle_variation = math.sin(time_factor * 2 * math.pi) * 0.2  # ±0.2ラジアンの変動
            angle = (angle + angle_variation) % (2 * math.pi)
            
            # 距離を部屋のサイズに合わせて調整
            # RSSIベースの距離を使いつつ、部屋のサイズに収まるようにスケール
            max_radius = min(facility_width, facility_height) * 0.4  # 部屋の40%の半径内に配置
            
            # RSSIに基づく距離（信号が強いほど近い）
            # -30 ~ -90 dBmを0.5 ~ max_radiusにマッピング
            normalized_rssi = (device.rssi + 90) / 60.0  # 0 ~ 1に正規化（-90が0、-30が1）
            adjusted_distance = max_radius * (1.0 - normalized_rssi * 0.8)  # 近いほど中心に
            
            # 少しランダム性を追加して自然な配置に
            distance_variation = math.sin(time_factor * 2 * math.pi) * 0.5
            adjusted_distance = max(0.5, adjusted_distance + distance_variation)
            
            estimated_x = receiver_x + adjusted_distance * math.cos(angle)
            estimated_y = receiver_y + adjusted_distance * math.sin(angle)
            
            # デバッグ用ログ（最初の5台のみ）
            if len(self.device_manager.devices) <= 5:
                self.logger.info(f"Device position - MAC: {device.mac_address[:8]}..., Angle: {angle:.2f} rad, Distance: {adjusted_distance:.2f}m, Position: ({estimated_x:.2f}, {estimated_y:.2f})")
            
            # 施設の境界内に制限
            estimated_x = max(0, min(estimated_x, facility_width))
            estimated_y = max(0, min(estimated_y, facility_height))
            
            position = (estimated_x, estimated_y)
            
            # ゾーン判定
            zone_id = self.position_calculator.get_zone_id(position)
            
            # デバイスマネージャーを更新
            self.device_manager.update_position(device_obj.device_id, position, zone_id)
            
            # データベースにデバイスを保存（推定位置付き）
            if self.data_integration and self.data_integration.is_connected:
                saved = await self.data_integration.save_device(
                    device_id=device_obj.device_id,
                    mac_address=device_obj.mac_address,
                    device_name=device_obj.device_name,
                    position=position,
                    zone_id=zone_id,
                    rssi=device.rssi
                )
                if saved:
                    self.logger.info(f"[SAVED] デバイス {device_obj.device_id} をデータベースに保存")
                else:
                    self.logger.warning(f"[FAILED] デバイス {device_obj.device_id} の保存に失敗")
            else:
                self.logger.debug(f"データベース未接続: デバイス {device_obj.device_id} はメモリのみ")
            
            self.logger.debug(
                f"Device {device_obj.device_id} detected at ~{distance:.1f}m"
            )
            
    async def _update_device_position(self, device_id: str, 
                                     position: tuple, 
                                     zone_id: Optional[str]):
        """
        デバイス位置を更新
        
        Args:
            device_id: デバイスID
            position: 位置座標
            zone_id: ゾーンID
        """
        timestamp = datetime.now()
        
        # デバイスマネージャーを更新
        self.device_manager.update_position(device_id, position, zone_id)
        
        # 信頼度を計算（受信機数は1とする）
        confidence = self._calculate_position_confidence(
            position, device_id, timestamp, 1
        )
        
        # 軌跡分析に追加
        self.trajectory_analyzer.add_position(
            device_id=device_id,
            position=position,
            timestamp=timestamp,
            zone_id=zone_id,
            confidence=confidence
        )
        
        # 滞留時間分析を更新
        self.dwell_analyzer.update_position(device_id, zone_id, timestamp)
        
        # フロー分析を更新（ゾーン遷移時間追跡）
        self.flow_analyzer.update_device_zone(device_id, zone_id, timestamp)
        
        # データベースに保存
        if self.data_integration and self.data_integration.is_connected:
            await self.data_integration.save_position(
                device_id=device_id,
                position=position,
                zone_id=zone_id,
                confidence=confidence,
                timestamp=timestamp
            )
        
    async def _analysis_loop(self):
        """分析ループ"""
        analysis_interval = 5.0  # 5秒ごとに分析
        
        while self.is_running:
            try:
                # アクティブデバイスを取得
                active_devices = self.device_manager.get_active_devices()
                
                # 軌跡を確定（非アクティブになったデバイス）
                for device_id in list(self.trajectory_analyzer.active_points.keys()):
                    device = self.device_manager.get_device(device_id)
                    if device and device not in active_devices:
                        trajectory = self.trajectory_analyzer.finalize_trajectory(device_id)
                        
                        if trajectory:
                            # フロー分析に追加
                            for i in range(len(trajectory.zones_visited) - 1):
                                from_zone = trajectory.zones_visited[i]
                                to_zone = trajectory.zones_visited[i + 1]
                                
                                self.flow_analyzer.add_transition(
                                    device_id=device_id,
                                    from_zone=from_zone,
                                    to_zone=to_zone,
                                    timestamp=datetime.now(),
                                    duration=10.0  # TODO: 実際の遷移時間
                                )
                                
                                # データベースにフロー遷移を保存
                                if self.data_integration and self.data_integration.is_connected:
                                    await self.data_integration.save_flow_transition(
                                        device_id=device_id,
                                        from_zone=from_zone,
                                        to_zone=to_zone,
                                        timestamp=datetime.now(),
                                        duration=10.0
                                    )
                                
                # 統計情報をログ
                self._log_statistics()
                
                await asyncio.sleep(analysis_interval)
                
            except Exception as e:
                self.logger.error(f"分析エラー: {e}")
                await asyncio.sleep(10)
                
    async def _maintenance_loop(self):
        """メンテナンスループ"""
        maintenance_interval = 3600  # 1時間ごと
        
        while self.is_running:
            try:
                # 古いデバイスをクリーンアップ
                removed = self.device_manager.cleanup_old_devices(days=7)
                if removed > 0:
                    self.logger.info(f"古いデバイスを{removed}件削除しました")
                    
                await asyncio.sleep(maintenance_interval)
                
            except Exception as e:
                self.logger.error(f"メンテナンスエラー: {e}")
                await asyncio.sleep(maintenance_interval)
                
    async def _reporting_loop(self):
        """レポート生成ループ"""
        reporting_interval = 300  # 5分ごと
        
        while self.is_running:
            try:
                # レポート生成（実装は省略）
                await asyncio.sleep(reporting_interval)
                
            except Exception as e:
                self.logger.error(f"レポートエラー: {e}")
                await asyncio.sleep(reporting_interval)
                
    def _log_statistics(self):
        """統計情報をログ出力"""
        device_stats = self.device_manager.get_statistics()
        trajectory_stats = self.trajectory_analyzer.get_statistics()
        dwell_stats = self.dwell_analyzer.get_statistics()
        flow_stats = self.flow_analyzer.get_statistics()
        
        log_msg = (
            f"統計情報 - "
            f"デバイス: {device_stats['active_devices']}/{device_stats['total_devices']}, "
            f"軌跡: {trajectory_stats['total_trajectories']}, "
            f"滞留: {dwell_stats['active_dwells']}, "
            f"遷移: {flow_stats['total_transitions']}"
        )
        
        # データベース統合の統計も追加
        if self.data_integration:
            db_stats = self.data_integration.get_statistics()
            if db_stats['is_connected']:
                log_msg += (
                    f", DB保存: デバイス={db_stats['devices_saved']}, "
                    f"位置={db_stats['positions_saved']}, "
                    f"エラー={db_stats['db_errors']}"
                )
            else:
                log_msg += ", DB: 未接続"
        
        self.logger.info(log_msg)
    
    def _calculate_position_confidence(
        self,
        position: Tuple[float, float],
        device_id: str,
        timestamp: datetime,
        receiver_count: int
    ) -> float:
        """
        位置の信頼度を計算
        
        Args:
            position: 計算された位置
            device_id: デバイスID
            timestamp: タイムスタンプ
            receiver_count: 受信機数
            
        Returns:
            信頼度（0.0-1.0）
        """
        confidence = 0.5  # 基本信頼度
        
        # 受信機数による信頼度調整
        if receiver_count >= 3:
            confidence += 0.3  # 三点測位が可能
        elif receiver_count == 2:
            confidence += 0.1  # 二点測位
        else:
            confidence -= 0.2  # 単一受信機
        
        # 履歴データとの一貫性チェック
        device_info = self.device_manager.get_device(device_id)
        if device_info and len(device_info.position_history) > 0:
            last_entry = device_info.position_history[-1]
            # position_historyはタプルのリスト: (datetime, (x, y))
            if isinstance(last_entry, tuple) and len(last_entry) == 2:
                last_timestamp, last_position = last_entry
                if isinstance(last_position, tuple) and len(last_position) == 2:
                    distance = np.sqrt(
                        (position[0] - last_position[0]) ** 2 +
                        (position[1] - last_position[1]) ** 2
                    )
                    
                    # 時間差を計算
                    time_diff = (timestamp - last_timestamp).total_seconds()
                else:
                    # 位置データが不正な場合はスキップ
                    distance = 0
                    time_diff = 1
            else:
                # データ形式が不正な場合はスキップ
                distance = 0
                time_diff = 1
            
            if time_diff > 0:
                # 速度を計算（m/s）
                velocity = distance / time_diff
                
                # 現実的な移動速度（人間の歩行速度：約1.4m/s）
                if velocity <= 2.0:  # 速歩程度まで
                    confidence += 0.1
                elif velocity <= 5.0:  # 小走り程度
                    confidence += 0.05
                else:  # 非現実的な速度
                    confidence -= 0.2
        
        # カルマンフィルターの共分散による調整
        if hasattr(self.position_calculator, 'kalman_filters'):
            kf = self.position_calculator.kalman_filters.get(device_id)
            if kf is not None:
                # 共分散行列のトレースが小さいほど信頼度が高い
                covariance_trace = np.trace(kf.P[:2, :2])
                if covariance_trace < 1.0:
                    confidence += 0.1
                elif covariance_trace < 5.0:
                    confidence += 0.05
                else:
                    confidence -= 0.05
        
        # 信頼度を0.0-1.0の範囲に制限
        return max(0.0, min(1.0, confidence))


async def main():
    """メイン関数"""
    system = MotionAnalysisSystem()
    
    # シグナルハンドラー設定
    def signal_handler(sig, frame):
        asyncio.create_task(system.stop())
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 初期化
        await system.initialize()
        
        # システム開始
        await system.start()
        
    except KeyboardInterrupt:
        print("\n終了シグナルを受信しました")
    except Exception as e:
        logging.error(f"システムエラー: {e}")
        sys.exit(1)
    finally:
        await system.stop()


if __name__ == "__main__":
    # Windows環境でのイベントループポリシー設定（test_bluetooth_foldio_style.pyと同じ）
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    asyncio.run(main())