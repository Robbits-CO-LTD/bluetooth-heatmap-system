"""DeviceManagerのユニットテスト"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# プロジェクトルートをパスに追加
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.device_manager import DeviceManager, Device


class TestDeviceManager:
    """DeviceManagerのテストクラス"""
    
    @pytest.fixture
    def sample_config(self):
        """サンプル設定"""
        return {
            'timeout': 300,  # 5分
            'max_history': 100,
            'anonymize': True,
            'salt_rotation_hours': 24
        }
    
    @pytest.fixture
    def device_manager(self, sample_config):
        """DeviceManagerインスタンス"""
        return DeviceManager(sample_config)
    
    def test_initialization(self, device_manager):
        """初期化テスト"""
        assert device_manager.timeout == 300
        assert device_manager.max_history == 100
        assert device_manager.anonymize == True
        assert len(device_manager.devices) == 0
    
    def test_hash_mac_address(self, device_manager):
        """MACアドレスハッシュ化テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        
        # 同じMACアドレスは同じハッシュを生成
        hash1 = device_manager._hash_mac(mac)
        hash2 = device_manager._hash_mac(mac)
        assert hash1 == hash2
        
        # 異なるMACアドレスは異なるハッシュを生成
        hash3 = device_manager._hash_mac("11:22:33:44:55:66")
        assert hash1 != hash3
        
        # ハッシュは16文字
        assert len(hash1) == 16
    
    def test_update_device_new(self, device_manager):
        """新規デバイス更新テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        rssi = -70
        name = "Test Device"
        
        device = device_manager.update_device(mac, rssi, name)
        
        assert device is not None
        assert device.device_id == device_manager._hash_mac(mac)
        assert device.rssi == rssi
        assert device.device_name == name
        assert device.is_active == True
        assert len(device_manager.devices) == 1
    
    def test_update_device_existing(self, device_manager):
        """既存デバイス更新テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        
        # 初回更新
        device1 = device_manager.update_device(mac, -70, "Device1")
        first_seen = device1.first_seen
        
        # 2回目更新
        device2 = device_manager.update_device(mac, -65, "Device1")
        
        assert device1.device_id == device2.device_id
        assert device2.rssi == -65
        assert device2.first_seen == first_seen
        assert device2.last_seen > first_seen
        assert len(device_manager.devices) == 1
    
    def test_update_position(self, device_manager):
        """位置更新テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        device = device_manager.update_device(mac, -70)
        
        # 位置を更新
        position = (10.5, 20.3)
        zone = "zone1"
        device_manager.update_position(device.device_id, position, zone)
        
        assert device.current_position == position
        assert device.current_zone == zone
        assert len(device.position_history) == 1
        assert device.position_history[0]['position'] == position
        assert device.position_history[0]['zone'] == zone
    
    def test_position_history_limit(self, device_manager):
        """位置履歴制限テスト"""
        device_manager.max_history = 5
        mac = "AA:BB:CC:DD:EE:FF"
        device = device_manager.update_device(mac, -70)
        
        # 制限を超えて位置を追加
        for i in range(10):
            device_manager.update_position(device.device_id, (i, i), f"zone{i}")
        
        # 履歴は最大5件
        assert len(device.position_history) == 5
        # 最新の5件が保持される
        assert device.position_history[-1]['position'] == (9, 9)
        assert device.position_history[0]['position'] == (5, 5)
    
    def test_get_active_devices(self, device_manager):
        """アクティブデバイス取得テスト"""
        # 複数デバイスを追加
        device1 = device_manager.update_device("AA:BB:CC:DD:EE:FF", -70)
        device2 = device_manager.update_device("11:22:33:44:55:66", -75)
        
        # 1つのデバイスを非アクティブに
        device1.last_seen = datetime.now() - timedelta(seconds=400)
        device1.is_active = False
        
        active_devices = device_manager.get_active_devices()
        
        assert len(active_devices) == 1
        assert active_devices[0].device_id == device2.device_id
    
    def test_get_device_by_id(self, device_manager):
        """ID指定デバイス取得テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        device = device_manager.update_device(mac, -70)
        
        # 存在するデバイス
        found = device_manager.get_device(device.device_id)
        assert found is not None
        assert found.device_id == device.device_id
        
        # 存在しないデバイス
        not_found = device_manager.get_device("invalid_id")
        assert not_found is None
    
    def test_cleanup_inactive_devices(self, device_manager):
        """非アクティブデバイスクリーンアップテスト"""
        # デバイスを追加
        device1 = device_manager.update_device("AA:BB:CC:DD:EE:FF", -70)
        device2 = device_manager.update_device("11:22:33:44:55:66", -75)
        
        # 1つを古いタイムスタンプに設定
        device1.last_seen = datetime.now() - timedelta(seconds=400)
        
        # クリーンアップ実行
        device_manager.cleanup_inactive()
        
        assert len(device_manager.devices) == 2
        assert device1.is_active == False
        assert device2.is_active == True
    
    def test_calculate_distance_traveled(self, device_manager):
        """移動距離計算テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        device = device_manager.update_device(mac, -70)
        
        # 位置を順次更新
        device_manager.update_position(device.device_id, (0, 0), "zone1")
        device_manager.update_position(device.device_id, (3, 4), "zone1")  # 5m移動
        device_manager.update_position(device.device_id, (3, 8), "zone2")  # 4m移動
        
        distance = device.calculate_distance_traveled()
        
        # 合計9m移動
        assert pytest.approx(distance, 0.1) == 9.0
    
    def test_get_statistics(self, device_manager):
        """統計情報取得テスト"""
        # デバイスを追加
        device_manager.update_device("AA:BB:CC:DD:EE:FF", -70, "iPhone")
        device_manager.update_device("11:22:33:44:55:66", -75, "Android")
        device_manager.update_device("22:33:44:55:66:77", -80, "Beacon")
        
        # 1つを非アクティブに
        device = device_manager.get_device(device_manager._hash_mac("22:33:44:55:66:77"))
        device.is_active = False
        
        stats = device_manager.get_statistics()
        
        assert stats['total_devices'] == 3
        assert stats['active_devices'] == 2
        assert stats['inactive_devices'] == 1
        assert 'average_rssi' in stats
    
    def test_anonymize_disabled(self):
        """匿名化無効時のテスト"""
        config = {
            'timeout': 300,
            'max_history': 100,
            'anonymize': False,  # 匿名化無効
            'salt_rotation_hours': 24
        }
        
        manager = DeviceManager(config)
        mac = "AA:BB:CC:DD:EE:FF"
        
        device = manager.update_device(mac, -70)
        
        # 匿名化が無効の場合、元のMACアドレスが保持される
        assert device.mac_address == mac
    
    def test_device_type_detection(self, device_manager):
        """デバイスタイプ検出テスト"""
        # iPhoneタイプ
        device1 = device_manager.update_device("AA:BB:CC:DD:EE:FF", -70, "iPhone")
        assert device1.device_type == "smartphone"
        
        # Androidタイプ
        device2 = device_manager.update_device("11:22:33:44:55:66", -75, "Android Device")
        assert device2.device_type == "smartphone"
        
        # Beaconタイプ
        device3 = device_manager.update_device("22:33:44:55:66:77", -80, "iBeacon")
        assert device3.device_type == "beacon"
        
        # 不明なタイプ
        device4 = device_manager.update_device("33:44:55:66:77:88", -85, "Unknown")
        assert device4.device_type == "unknown"
    
    def test_concurrent_updates(self, device_manager):
        """同時更新テスト"""
        mac = "AA:BB:CC:DD:EE:FF"
        
        # 同じデバイスを複数回更新
        for i in range(10):
            device_manager.update_device(mac, -70 + i)
        
        # デバイスは1つのみ存在
        assert len(device_manager.devices) == 1
        
        device = list(device_manager.devices.values())[0]
        # 最後のRSSI値が保持される
        assert device.rssi == -61


if __name__ == "__main__":
    pytest.main([__file__, "-v"])