"""Bluetoothスキャナーモジュール"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


@dataclass
class DetectedDevice:
    """検出されたデバイス"""
    mac_address: str
    device_name: Optional[str]
    rssi: int
    timestamp: datetime
    receiver_id: str
    raw_data: Optional[Dict] = None
    manufacturer_data: Optional[Dict] = None
    service_data: Optional[Dict] = None
    
    @property
    def signal_strength(self) -> str:
        """信号強度のカテゴリを返す"""
        if self.rssi > -50:
            return "very_strong"
        elif self.rssi > -70:
            return "strong"
        elif self.rssi > -85:
            return "medium"
        else:
            return "weak"


class BluetoothScanner:
    """Bluetoothデバイススキャナー"""
    
    def __init__(self, config: Dict, receiver_id: str = "default"):
        """
        初期化
        
        Args:
            config: スキャン設定
            receiver_id: 受信機ID
        """
        self.config = config
        self.receiver_id = receiver_id
        self.logger = logging.getLogger(__name__)
        
        # スキャン設定
        self.scan_interval = config.get('interval', 1.0)
        self.scan_duration = config.get('duration', 5.0)
        self.rssi_threshold = config.get('rssi_threshold', -90)
        self.device_timeout = config.get('device_timeout', 30.0)
        
        # デバイスキャッシュ
        self.detected_devices: Dict[str, DetectedDevice] = {}
        self.device_history: List[DetectedDevice] = []
        
        # スキャン状態
        self.is_scanning = False
        self.scanner = None
        self._scan_task = None
        
    async def start(self) -> None:
        """スキャン開始"""
        if self.is_scanning:
            self.logger.warning("Scanner is already running")
            return
            
        self.is_scanning = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        self.logger.info(f"Bluetooth scanner started (receiver: {self.receiver_id})")
        
    async def stop(self) -> None:
        """スキャン停止"""
        self.is_scanning = False
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
                
        if self.scanner:
            await self.scanner.stop()
            
        self.logger.info(f"Bluetooth scanner stopped (receiver: {self.receiver_id})")
        
    async def _scan_loop(self) -> None:
        """スキャンループ"""
        while self.is_scanning:
            try:
                await self._perform_scan()
                await asyncio.sleep(self.scan_interval)
                
                # タイムアウトしたデバイスをクリーンアップ
                self._cleanup_old_devices()
                
            except Exception as e:
                self.logger.error(f"Scan error: {e}")
                await asyncio.sleep(5)  # エラー時は少し待つ
                
    async def _perform_scan(self) -> None:
        """単一スキャンを実行"""
        try:
            self.logger.info(f"Starting BLE scan (duration: {self.scan_duration}s)")
            
            # BleakScannerでスキャン (test_bluetooth_foldio_style.pyと同じ方式)
            devices = await BleakScanner.discover(timeout=self.scan_duration)
            
            current_time = datetime.now()
            detected_count = 0
            
            # デバイスリストを処理
            for device in devices:
                # RSSIを取得（属性がない場合はデフォルト値）
                rssi = device.rssi if hasattr(device, 'rssi') and device.rssi else -70
                
                # RSSI閾値チェック
                if rssi < self.rssi_threshold:
                    continue
                
                # デバイス名（Noneの場合は"Unknown"）
                device_name = device.name if device.name else "Unknown Device"
                    
                # デバイス情報を作成
                detected_device = DetectedDevice(
                    mac_address=device.address,
                    device_name=device_name,
                    rssi=rssi,
                    timestamp=current_time,
                    receiver_id=self.receiver_id,
                    manufacturer_data={},
                    service_data={}
                )
                
                # キャッシュに保存
                self.detected_devices[device.address] = detected_device
                self.device_history.append(detected_device)
                detected_count += 1
                
                self.logger.info(
                    f"Detected device: {device.address} "
                    f"(RSSI: {rssi} dBm, Name: {device_name})"
                )
            
            if detected_count == 0:
                self.logger.warning(
                    f"No devices detected in this scan. "
                    f"Check: 1) Bluetooth is ON, 2) Devices are in range, "
                    f"3) RSSI threshold ({self.rssi_threshold} dBm)"
                )
            else:
                self.logger.info(f"Scan completed: {detected_count} devices detected")
                
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            self.logger.error("Try running with administrator privileges on Windows")
            
    def _cleanup_old_devices(self) -> None:
        """古いデバイス情報をクリーンアップ"""
        current_time = datetime.now()
        timeout_threshold = current_time - timedelta(seconds=self.device_timeout)
        
        # タイムアウトしたデバイスを削除
        expired_devices = [
            mac for mac, device in self.detected_devices.items()
            if device.timestamp < timeout_threshold
        ]
        
        for mac in expired_devices:
            del self.detected_devices[mac]
            self.logger.debug(f"Device timeout: {mac}")
            
        # 履歴のサイズを制限（直近1000件）
        if len(self.device_history) > 1000:
            self.device_history = self.device_history[-1000:]
            
    def get_current_devices(self) -> List[DetectedDevice]:
        """現在検出中のデバイスリストを取得"""
        return list(self.detected_devices.values())
        
    def get_device_count(self) -> int:
        """現在検出中のデバイス数を取得"""
        return len(self.detected_devices)
        
    def get_device_by_mac(self, mac_address: str) -> Optional[DetectedDevice]:
        """MACアドレスでデバイスを取得"""
        return self.detected_devices.get(mac_address)
        
    def estimate_distance(self, rssi: int, tx_power: int = -59) -> float:
        """
        RSSIから距離を推定
        
        Args:
            rssi: 受信信号強度
            tx_power: 送信電力（1メートルでのRSSI）
            
        Returns:
            推定距離（メートル）
        """
        # Path Loss Exponent (環境による、通常2-4)
        n = 2.5
        
        # 距離計算
        distance = 10 ** ((tx_power - rssi) / (10 * n))
        
        return round(distance, 2)
        
    def get_zone_devices(self, zone_polygon: List[Tuple[float, float]]) -> List[DetectedDevice]:
        """
        特定ゾーン内のデバイスを取得
        
        Args:
            zone_polygon: ゾーンのポリゴン座標
            
        Returns:
            ゾーン内のデバイスリスト
        """
        # TODO: 位置計算後にゾーン判定を実装
        return []
        
    def get_statistics(self) -> Dict:
        """統計情報を取得"""
        if not self.detected_devices:
            return {
                'total_devices': 0,
                'avg_rssi': 0,
                'signal_distribution': {}
            }
            
        rssi_values = [d.rssi for d in self.detected_devices.values()]
        signal_dist = {}
        
        for device in self.detected_devices.values():
            strength = device.signal_strength
            signal_dist[strength] = signal_dist.get(strength, 0) + 1
            
        return {
            'total_devices': len(self.detected_devices),
            'avg_rssi': sum(rssi_values) / len(rssi_values),
            'min_rssi': min(rssi_values),
            'max_rssi': max(rssi_values),
            'signal_distribution': signal_dist,
            'receiver_id': self.receiver_id
        }


class MultiReceiverScanner:
    """複数受信機対応スキャナー"""
    
    def __init__(self, config: Dict, receiver_configs: List[Dict]):
        """
        初期化
        
        Args:
            config: 共通スキャン設定
            receiver_configs: 受信機ごとの設定リスト
        """
        self.config = config
        self.scanners = {}
        self.logger = logging.getLogger(__name__)
        
        # 各受信機用のスキャナーを作成
        for receiver_config in receiver_configs:
            receiver_id = receiver_config['id']
            scanner = BluetoothScanner(config, receiver_id)
            self.scanners[receiver_id] = scanner
            
    async def start_all(self) -> None:
        """全スキャナーを開始"""
        tasks = []
        for scanner in self.scanners.values():
            tasks.append(scanner.start())
            
        await asyncio.gather(*tasks)
        self.logger.info(f"Started {len(self.scanners)} scanners")
        
    async def stop_all(self) -> None:
        """全スキャナーを停止"""
        tasks = []
        for scanner in self.scanners.values():
            tasks.append(scanner.stop())
            
        await asyncio.gather(*tasks)
        self.logger.info(f"Stopped {len(self.scanners)} scanners")
        
    def get_all_devices(self) -> Dict[str, List[DetectedDevice]]:
        """全受信機のデバイス情報を取得"""
        result = {}
        for receiver_id, scanner in self.scanners.items():
            result[receiver_id] = scanner.get_current_devices()
            
        return result
        
    def get_merged_devices(self) -> List[DetectedDevice]:
        """全受信機のデバイス情報をマージして取得"""
        merged = {}
        
        for scanner in self.scanners.values():
            for device in scanner.get_current_devices():
                mac = device.mac_address
                
                # より強い信号のデバイスを優先
                if mac not in merged or device.rssi > merged[mac].rssi:
                    merged[mac] = device
                    
        return list(merged.values())