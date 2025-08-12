"""PositionCalculatorのユニットテスト"""
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

# プロジェクトルートをパスに追加
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.position_calculator import PositionCalculator, ReceiverMeasurement


class TestPositionCalculator:
    """PositionCalculatorのテストクラス"""
    
    @pytest.fixture
    def sample_config(self):
        """サンプル設定"""
        return {
            'algorithm': 'trilateration',
            'rssi_at_1m': -59,
            'path_loss_exponent': 2.0,
            'confidence_threshold': 0.5,
            'smoothing_window': 5
        }
    
    @pytest.fixture
    def sample_layout(self):
        """サンプルレイアウト"""
        return {
            'receivers': [
                {'id': 'rx1', 'position': [0, 0]},
                {'id': 'rx2', 'position': [10, 0]},
                {'id': 'rx3', 'position': [5, 10]}
            ],
            'zones': [
                {
                    'id': 'zone1',
                    'name': 'Zone 1',
                    'polygon': [[0, 0], [10, 0], [10, 10], [0, 10]]
                },
                {
                    'id': 'zone2',
                    'name': 'Zone 2',
                    'polygon': [[10, 0], [20, 0], [20, 10], [10, 10]]
                }
            ]
        }
    
    def test_initialization(self, sample_config, sample_layout):
        """初期化テスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        assert calculator.algorithm == 'trilateration'
        assert calculator.rssi_at_1m == -59
        assert calculator.path_loss_exponent == 2.0
        assert len(calculator.receivers) == 3
        assert len(calculator.zones) == 2
    
    def test_rssi_to_distance(self, sample_config, sample_layout):
        """RSSI距離変換テスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # RSSI = -59 (1メートル)
        distance = calculator._rssi_to_distance(-59)
        assert pytest.approx(distance, 0.1) == 1.0
        
        # RSSI = -79 (10メートル)
        distance = calculator._rssi_to_distance(-79)
        assert pytest.approx(distance, 0.1) == 10.0
    
    def test_trilateration_perfect_case(self, sample_config, sample_layout):
        """三点測位（理想的なケース）のテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 位置 (5, 5) からの測定値
        measurements = [
            ReceiverMeasurement('rx1', -72.0),  # 約7.07m
            ReceiverMeasurement('rx2', -72.0),  # 約7.07m
            ReceiverMeasurement('rx3', -68.5)   # 約5m
        ]
        
        position = calculator.calculate_position(measurements)
        
        assert position is not None
        x, y = position
        assert pytest.approx(x, abs=1.0) == 5.0
        assert pytest.approx(y, abs=1.0) == 5.0
    
    def test_trilateration_insufficient_receivers(self, sample_config, sample_layout):
        """受信機不足の場合のテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 2つの受信機のみ
        measurements = [
            ReceiverMeasurement('rx1', -70),
            ReceiverMeasurement('rx2', -70)
        ]
        
        position = calculator.calculate_position(measurements)
        
        # 受信機が3つ未満の場合は重心を返す
        assert position is not None
    
    def test_weighted_centroid(self, sample_config, sample_layout):
        """重み付き重心アルゴリズムのテスト"""
        sample_config['algorithm'] = 'weighted_centroid'
        calculator = PositionCalculator(sample_config, sample_layout)
        
        measurements = [
            ReceiverMeasurement('rx1', -60),  # 強い信号
            ReceiverMeasurement('rx2', -70),  # 中程度の信号
            ReceiverMeasurement('rx3', -80)   # 弱い信号
        ]
        
        position = calculator.calculate_position(measurements)
        
        assert position is not None
        x, y = position
        # rx1により近い位置になるはず
        assert x < 5.0
        assert y < 5.0
    
    def test_kalman_filter(self, sample_config, sample_layout):
        """カルマンフィルタのテスト"""
        sample_config['algorithm'] = 'kalman'
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 初回測定
        measurements1 = [
            ReceiverMeasurement('rx1', -70),
            ReceiverMeasurement('rx2', -70),
            ReceiverMeasurement('rx3', -70)
        ]
        
        position1 = calculator.calculate_position(measurements1)
        assert position1 is not None
        
        # 2回目測定（わずかに移動）
        measurements2 = [
            ReceiverMeasurement('rx1', -71),
            ReceiverMeasurement('rx2', -69),
            ReceiverMeasurement('rx3', -70)
        ]
        
        position2 = calculator.calculate_position(measurements2)
        assert position2 is not None
        
        # カルマンフィルタによりスムージングされているはず
        x1, y1 = position1
        x2, y2 = position2
        distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        assert distance < 5.0  # 大きな変化はないはず
    
    def test_get_zone(self, sample_config, sample_layout):
        """ゾーン判定テスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # Zone 1内の点
        zone = calculator.get_zone((5, 5))
        assert zone == 'zone1'
        
        # Zone 2内の点
        zone = calculator.get_zone((15, 5))
        assert zone == 'zone2'
        
        # どのゾーンにも属さない点
        zone = calculator.get_zone((25, 25))
        assert zone is None
    
    def test_point_in_polygon(self, sample_config, sample_layout):
        """ポリゴン内判定テスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 正方形ポリゴン
        polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
        
        # 内部の点
        assert calculator._point_in_polygon((5, 5), polygon) == True
        
        # 境界上の点
        assert calculator._point_in_polygon((0, 0), polygon) == True
        
        # 外部の点
        assert calculator._point_in_polygon((15, 15), polygon) == False
        assert calculator._point_in_polygon((-5, 5), polygon) == False
    
    def test_empty_measurements(self, sample_config, sample_layout):
        """測定値が空の場合のテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        position = calculator.calculate_position([])
        assert position is None
    
    def test_invalid_receiver_id(self, sample_config, sample_layout):
        """無効な受信機IDのテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        measurements = [
            ReceiverMeasurement('invalid_rx', -70),
            ReceiverMeasurement('rx1', -70)
        ]
        
        # 無効な受信機は無視される
        position = calculator.calculate_position(measurements)
        assert position is not None
    
    def test_extreme_rssi_values(self, sample_config, sample_layout):
        """極端なRSSI値のテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 非常に強い信号
        distance = calculator._rssi_to_distance(-30)
        assert distance > 0
        assert distance < 1.0
        
        # 非常に弱い信号
        distance = calculator._rssi_to_distance(-100)
        assert distance > 0
        assert distance < 1000.0
    
    def test_confidence_calculation(self, sample_config, sample_layout):
        """信頼度計算のテスト"""
        calculator = PositionCalculator(sample_config, sample_layout)
        
        # 3つの受信機からの測定（高信頼度）
        measurements_high = [
            ReceiverMeasurement('rx1', -65),
            ReceiverMeasurement('rx2', -65),
            ReceiverMeasurement('rx3', -65)
        ]
        
        position = calculator.calculate_position(measurements_high)
        assert position is not None
        
        # 1つの受信機のみ（低信頼度）
        measurements_low = [
            ReceiverMeasurement('rx1', -70)
        ]
        
        position = calculator.calculate_position(measurements_low)
        # 信頼度が低い場合でも位置は返す（フォールバック）


if __name__ == "__main__":
    pytest.main([__file__, "-v"])