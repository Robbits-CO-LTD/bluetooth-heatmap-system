"""デバイス管理モジュール"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np


@dataclass
class Device:
    """管理対象デバイス"""
    device_id: str  # 匿名化されたID
    mac_address: str  # 元のMACアドレス（プライバシー設定による）
    first_seen: datetime
    last_seen: datetime
    device_name: Optional[str] = None  # デバイス名
    device_type: str = "unknown"  # smartphone, wearable, beacon, etc.
    is_anonymous: bool = True
    total_detections: int = 0
    zones_visited: Set[str] = field(default_factory=set)
    current_zone: Optional[str] = None
    current_position: Optional[Tuple[float, float]] = None
    position_history: List[Tuple[datetime, Tuple[float, float]]] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class DeviceManager:
    """デバイス管理クラス"""
    
    def __init__(self, config: Dict):
        """
        初期化
        
        Args:
            config: デバイス管理設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # デバイス管理
        self.devices: Dict[str, Device] = {}  # device_id -> Device
        self.mac_to_id: Dict[str, str] = {}  # mac_address -> device_id
        self.current_scan_devices: Set[str] = set()  # 現在のスキャンで検出されたデバイスID
        self.previous_scan_devices: Set[str] = set()  # 前回のスキャンで検出されたデバイスID
        
        # プライバシー設定
        self.anonymize = config.get('anonymize', True)
        self.anonymize_after_hours = config.get('anonymize_after_hours', 24)
        self.salt = self._generate_salt()
        
        # デバイスタイプ判定用
        self.device_patterns = {
            'smartphone': ['iPhone', 'Android', 'Phone'],
            'wearable': ['Watch', 'Band', 'Fitbit'],
            'beacon': ['Beacon', 'iBeacon', 'Eddystone'],
            'laptop': ['MacBook', 'ThinkPad', 'Laptop'],
            'tablet': ['iPad', 'Tab', 'Tablet']
        }
        
        # 統計情報
        self.stats = {
            'total_devices': 0,
            'active_devices': 0,
            'new_devices_today': 0,
            'device_types': defaultdict(int)
        }
        
    def _generate_salt(self) -> str:
        """ソルト生成（日付ベースで固定）"""
        # 日付ベースの固定ソルトを生成（同じ日は同じソルト）
        date_str = datetime.now().strftime("%Y-%m-%d")
        return hashlib.sha256(
            f"bluetooth-heatmap-{date_str}-salt".encode()
        ).hexdigest()[:16]
        
    def _anonymize_mac(self, mac_address: str) -> str:
        """
        MACアドレスを匿名化
        
        Args:
            mac_address: MACアドレス
            
        Returns:
            匿名化されたID
        """
        if not self.anonymize:
            return mac_address
            
        # MACアドレスのみでハッシュ化（同じデバイスは常に同じID）
        # プライバシーのためMACアドレスを直接保存しない
        return hashlib.sha256(mac_address.encode()).hexdigest()[:16]
        
    def register_device(self, mac_address: str, 
                       device_name: Optional[str] = None,
                       rssi: int = 0,
                       check_duplicate: bool = True) -> Optional[Device]:
        """
        デバイスを登録（重複チェック付き）
        
        Args:
            mac_address: MACアドレス
            device_name: デバイス名
            rssi: 信号強度
            check_duplicate: 重複チェックを行うか
            
        Returns:
            新規登録されたデバイス（既存デバイスの場合はNone）
        """
        # デバイスIDを生成
        device_id = self._anonymize_mac(mac_address)
        
        # 現在のスキャンで既に処理済みかチェック
        if check_duplicate and device_id in self.current_scan_devices:
            # スキャン内で再度検出された場合もカウントアップ
            if device_id in self.devices:
                device = self.devices[device_id]
                device.last_seen = datetime.now()
                device.total_detections += 1
            self.logger.debug(f"Device {device_id} already processed in current scan")
            return None
        
        # 既存デバイスチェック
        if mac_address in self.mac_to_id:
            existing_device_id = self.mac_to_id[mac_address]
            
            # 同じデバイスIDの場合のみ更新（重複防止）
            if existing_device_id == device_id:
                device = self.devices[device_id]
                
                # 最終検出時刻を更新
                device.last_seen = datetime.now()
                device.total_detections += 1
                
                # デバイス名が提供されていて、まだ設定されていない場合は更新
                if device_name and not device.device_name:
                    device.device_name = device_name
                    device.device_type = self._detect_device_type(device_name)
                
                # 現在のスキャンで検出されたことを記録
                self.current_scan_devices.add(device_id)
                
                self.logger.debug(f"Existing device updated: {device_id}")
                return None  # 既存デバイスの場合はNoneを返す
            else:
                # 異なるデバイスIDの場合は登録しない（重複防止）
                self.logger.warning(f"Duplicate MAC address with different ID: {mac_address}")
                return None
            
        # 既にデバイスIDが存在する場合も重複チェック
        if device_id in self.devices:
            self.logger.debug(f"Device {device_id} already exists")
            self.current_scan_devices.add(device_id)
            # 既存デバイスを更新
            device = self.devices[device_id]
            device.last_seen = datetime.now()
            device.total_detections += 1
            if device_name and not device.device_name:
                device.device_name = device_name
                device.device_type = self._detect_device_type(device_name)
            return None  # 既存デバイスの場合はNoneを返す
            
        # 新規デバイス作成
        device_type = self._detect_device_type(device_name)
        
        device = Device(
            device_id=device_id,
            mac_address=mac_address if not self.anonymize else "",
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            device_name=device_name,
            device_type=device_type,
            is_anonymous=self.anonymize,
            total_detections=1
        )
        
        # 登録
        self.devices[device_id] = device
        self.mac_to_id[mac_address] = device_id
        self.current_scan_devices.add(device_id)
        
        # 統計更新
        self.stats['total_devices'] += 1
        self.stats['device_types'][device_type] += 1
        
        # 今日の新規デバイスかチェック
        if device.first_seen.date() == datetime.now().date():
            self.stats['new_devices_today'] += 1
            
        self.logger.info(f"New device registered: {device_id} (type: {device_type})")
        
        return device
        
    def _detect_device_type(self, device_name: Optional[str]) -> str:
        """
        デバイスタイプを検出
        
        Args:
            device_name: デバイス名
            
        Returns:
            デバイスタイプ
        """
        if not device_name:
            return "unknown"
            
        device_name_lower = device_name.lower()
        
        for device_type, patterns in self.device_patterns.items():
            for pattern in patterns:
                if pattern.lower() in device_name_lower:
                    return device_type
                    
        return "unknown"
    
    def start_new_scan(self):
        """新しいスキャンサイクルを開始"""
        # 前回のスキャンデバイスを保存
        self.previous_scan_devices = self.current_scan_devices.copy()
        # 現在のスキャンデバイスをクリア
        self.current_scan_devices.clear()
        self.logger.debug(f"New scan cycle started. Previous devices: {len(self.previous_scan_devices)}")
    
    def cleanup_undetected_devices(self) -> List[str]:
        """未検出デバイスをクリーンアップ
        
        Returns:
            削除されたデバイスIDのリスト
        """
        # 前回のスキャンにあって今回のスキャンにないデバイスを特定
        undetected_devices = self.previous_scan_devices - self.current_scan_devices
        removed_devices = []
        
        for device_id in undetected_devices:
            if device_id in self.devices:
                device = self.devices[device_id]
                # 最後の検出から一定時間経過していたら削除
                time_since_last_seen = (datetime.now() - device.last_seen).total_seconds()
                
                # 即座に削除（よりリアルタイムな表示のため）
                if time_since_last_seen > 5:  # 5秒以上検出されない場合（リアルタイム性向上）
                    # MACアドレスマッピングを削除
                    for mac, did in list(self.mac_to_id.items()):
                        if did == device_id:
                            del self.mac_to_id[mac]
                            break
                    
                    # デバイスを削除
                    del self.devices[device_id]
                    removed_devices.append(device_id)
                    
                    # 統計更新
                    self.stats['total_devices'] -= 1
                    if device.device_type in self.stats['device_types']:
                        self.stats['device_types'][device.device_type] -= 1
                    
                    self.logger.info(f"Device removed (not detected): {device_id}")
        
        return removed_devices
    
    def get_current_active_devices(self) -> List[Device]:
        """現在アクティブなデバイスのみを取得
        
        Returns:
            現在のスキャンで検出されたデバイスのリスト
        """
        active_devices = []
        for device_id in self.current_scan_devices:
            if device_id in self.devices:
                active_devices.append(self.devices[device_id])
        return active_devices
        
    def update_position(self, device_id: str, 
                       position: Tuple[float, float],
                       zone_id: Optional[str] = None) -> None:
        """
        デバイスの位置を更新
        
        Args:
            device_id: デバイスID
            position: 位置座標
            zone_id: ゾーンID
        """
        if device_id not in self.devices:
            self.logger.warning(f"Device not found: {device_id}")
            return
            
        device = self.devices[device_id]
        
        # 位置更新
        device.current_position = position
        device.position_history.append((datetime.now(), position))
        
        # 履歴サイズ制限（直近100件）
        if len(device.position_history) > 100:
            device.position_history = device.position_history[-100:]
            
        # ゾーン更新
        if zone_id:
            device.current_zone = zone_id
            device.zones_visited.add(zone_id)
            
    def get_device(self, device_id: str) -> Optional[Device]:
        """デバイス情報を取得"""
        return self.devices.get(device_id)
        
    def get_device_by_mac(self, mac_address: str) -> Optional[Device]:
        """MACアドレスからデバイスを取得"""
        device_id = self.mac_to_id.get(mac_address)
        if device_id:
            return self.devices.get(device_id)
        return None
        
    def get_active_devices(self, timeout_minutes: int = 5) -> List[Device]:
        """
        アクティブなデバイスを取得
        
        Args:
            timeout_minutes: タイムアウト時間（分）
            
        Returns:
            アクティブなデバイスリスト
        """
        current_time = datetime.now()
        timeout_threshold = current_time - timedelta(minutes=timeout_minutes)
        
        active_devices = [
            device for device in self.devices.values()
            if device.last_seen >= timeout_threshold
        ]
        
        self.stats['active_devices'] = len(active_devices)
        
        return active_devices
        
    def get_devices_in_zone(self, zone_id: str) -> List[Device]:
        """
        特定ゾーン内のデバイスを取得
        
        Args:
            zone_id: ゾーンID
            
        Returns:
            ゾーン内のデバイスリスト
        """
        return [
            device for device in self.get_active_devices()
            if device.current_zone == zone_id
        ]
        
    def get_device_trajectory(self, device_id: str,
                            start_time: Optional[datetime] = None,
                            end_time: Optional[datetime] = None) -> List[Tuple[datetime, Tuple[float, float]]]:
        """
        デバイスの軌跡を取得
        
        Args:
            device_id: デバイスID
            start_time: 開始時刻
            end_time: 終了時刻
            
        Returns:
            軌跡データ
        """
        device = self.devices.get(device_id)
        if not device:
            return []
            
        trajectory = device.position_history
        
        # 時間範囲でフィルタ
        if start_time:
            trajectory = [(t, p) for t, p in trajectory if t >= start_time]
        if end_time:
            trajectory = [(t, p) for t, p in trajectory if t <= end_time]
            
        return trajectory
        
    def cleanup_old_devices(self, days: int = 30) -> int:
        """
        古いデバイス情報をクリーンアップ
        
        Args:
            days: 保持日数
            
        Returns:
            削除されたデバイス数
        """
        current_time = datetime.now()
        threshold = current_time - timedelta(days=days)
        
        devices_to_remove = []
        
        for device_id, device in self.devices.items():
            if device.last_seen < threshold:
                devices_to_remove.append(device_id)
                
        # 削除実行
        for device_id in devices_to_remove:
            device = self.devices[device_id]
            if device.mac_address in self.mac_to_id:
                del self.mac_to_id[device.mac_address]
            del self.devices[device_id]
            
        if devices_to_remove:
            self.logger.info(f"Cleaned up {len(devices_to_remove)} old devices")
            
        return len(devices_to_remove)
        
    def get_statistics(self) -> Dict:
        """統計情報を取得"""
        active_devices = self.get_active_devices()
        
        # ゾーン別統計
        zone_stats = defaultdict(int)
        for device in active_devices:
            if device.current_zone:
                zone_stats[device.current_zone] += 1
                
        # デバイスタイプ別統計
        type_stats = defaultdict(int)
        for device in active_devices:
            type_stats[device.device_type] += 1
            
        return {
            'total_devices': self.stats['total_devices'],
            'active_devices': len(active_devices),
            'new_devices_today': self.stats['new_devices_today'],
            'device_types': dict(type_stats),
            'zones': dict(zone_stats),
            'avg_zones_visited': np.mean([len(d.zones_visited) for d in self.devices.values()]) if self.devices else 0,
            'timestamp': datetime.now().isoformat()
        }
        
    def export_anonymized_data(self) -> List[Dict]:
        """
        匿名化されたデータをエクスポート
        
        Returns:
            匿名化されたデバイスデータ
        """
        export_data = []
        
        for device in self.devices.values():
            export_data.append({
                'device_id': device.device_id,
                'device_type': device.device_type,
                'first_seen': device.first_seen.isoformat(),
                'last_seen': device.last_seen.isoformat(),
                'total_detections': device.total_detections,
                'zones_visited': list(device.zones_visited),
                'current_zone': device.current_zone
            })
            
        return export_data