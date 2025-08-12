"""位置計算モジュール"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from scipy.optimize import minimize
from scipy.spatial import distance


@dataclass
class ReceiverMeasurement:
    """受信機の測定データ"""
    receiver_id: str
    receiver_position: Tuple[float, float]
    rssi: int
    distance: float
    timestamp: float


class PositionCalculator:
    """位置計算クラス"""
    
    def __init__(self, config: Dict, layout: Dict):
        """
        初期化
        
        Args:
            config: 位置計算設定
            layout: 施設レイアウト
        """
        self.config = config
        self.layout = layout
        self.logger = logging.getLogger(__name__)
        
        # 設定パラメータ
        self.algorithm = config.get('algorithm', 'trilateration')
        self.min_receivers = config.get('min_receivers', 3)
        self.max_distance = config.get('max_distance', 50.0)
        self.smoothing_factor = config.get('smoothing_factor', 0.7)
        
        # 受信機位置マップ
        self.receiver_positions = {}
        for receiver in layout.get('receivers', []):
            self.receiver_positions[receiver['id']] = tuple(receiver['position'])
            
        # カルマンフィルタ用の状態
        self.kalman_states = {}
        
        # Path Loss Exponent (環境に応じて調整)
        self.path_loss_exponent = 2.5
        
    def calculate_position(self, measurements: List[ReceiverMeasurement]) -> Optional[Tuple[float, float]]:
        """
        複数の受信機の測定値から位置を計算
        
        Args:
            measurements: 受信機測定データのリスト
            
        Returns:
            推定位置座標 (x, y)
        """
        if len(measurements) < self.min_receivers:
            self.logger.warning(f"Not enough receivers: {len(measurements)} < {self.min_receivers}")
            return None
            
        # アルゴリズムに応じて位置計算
        if self.algorithm == 'trilateration':
            position = self._trilateration(measurements)
        elif self.algorithm == 'weighted_centroid':
            position = self._weighted_centroid(measurements)
        elif self.algorithm == 'kalman':
            position = self._kalman_filter(measurements)
        else:
            position = self._trilateration(measurements)
            
        # 施設範囲内にクリップ
        if position:
            position = self._clip_to_facility(position)
            
        return position
        
    def _trilateration(self, measurements: List[ReceiverMeasurement]) -> Optional[Tuple[float, float]]:
        """
        三辺測量による位置計算
        
        Args:
            measurements: 受信機測定データ
            
        Returns:
            推定位置
        """
        if len(measurements) < 3:
            return None
            
        # 最も強い信号の3つを使用
        measurements = sorted(measurements, key=lambda m: m.rssi, reverse=True)[:3]
        
        # 初期推定値（重心）
        x0 = np.mean([m.receiver_position[0] for m in measurements])
        y0 = np.mean([m.receiver_position[1] for m in measurements])
        initial_guess = [x0, y0]
        
        # 最小二乗法で位置を推定
        def objective(pos):
            x, y = pos
            error = 0
            for m in measurements:
                rx, ry = m.receiver_position
                predicted_distance = np.sqrt((x - rx)**2 + (y - ry)**2)
                error += (predicted_distance - m.distance)**2
            return error
            
        # 最適化
        result = minimize(objective, initial_guess, method='L-BFGS-B')
        
        if result.success:
            return tuple(result.x)
        else:
            self.logger.warning("Trilateration optimization failed")
            return None
            
    def _weighted_centroid(self, measurements: List[ReceiverMeasurement]) -> Tuple[float, float]:
        """
        重み付き重心による位置計算
        
        Args:
            measurements: 受信機測定データ
            
        Returns:
            推定位置
        """
        weights = []
        positions = []
        
        for m in measurements:
            # RSSIを重みとして使用（距離の逆数）
            weight = 1.0 / (m.distance + 0.1)  # 0除算を避ける
            weights.append(weight)
            positions.append(m.receiver_position)
            
        weights = np.array(weights)
        positions = np.array(positions)
        
        # 正規化
        weights = weights / np.sum(weights)
        
        # 重み付き平均
        weighted_position = np.sum(positions * weights[:, np.newaxis], axis=0)
        
        return tuple(weighted_position)
        
    def _kalman_filter(self, measurements: List[ReceiverMeasurement]) -> Optional[Tuple[float, float]]:
        """
        カルマンフィルタによる位置推定
        
        Args:
            measurements: 受信機測定データ
            
        Returns:
            推定位置
        """
        # デバイスIDが必要（簡略化のため最初の受信機IDを使用）
        device_id = measurements[0].receiver_id
        
        # 初期位置推定
        initial_position = self._weighted_centroid(measurements)
        
        if device_id not in self.kalman_states:
            # カルマンフィルタの初期化
            self.kalman_states[device_id] = {
                'x': np.array([initial_position[0], initial_position[1], 0, 0]),  # [x, y, vx, vy]
                'P': np.eye(4) * 10  # 共分散行列
            }
            
        state = self.kalman_states[device_id]
        
        # 状態遷移行列
        dt = 1.0  # 時間ステップ
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        # プロセスノイズ
        Q = np.eye(4) * 0.1
        
        # 予測ステップ
        x_pred = F @ state['x']
        P_pred = F @ state['P'] @ F.T + Q
        
        # 観測行列
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        
        # 観測ノイズ
        R = np.eye(2) * 1.0
        
        # 観測値
        z = np.array(initial_position)
        
        # 更新ステップ
        y = z - H @ x_pred  # 残差
        S = H @ P_pred @ H.T + R  # 残差共分散
        K = P_pred @ H.T @ np.linalg.inv(S)  # カルマンゲイン
        
        # 状態更新
        state['x'] = x_pred + K @ y
        state['P'] = (np.eye(4) - K @ H) @ P_pred
        
        return (state['x'][0], state['x'][1])
        
    def rssi_to_distance(self, rssi: int, tx_power: int = -59) -> float:
        """
        RSSIから距離を計算
        
        Args:
            rssi: 受信信号強度
            tx_power: 送信電力（1メートルでのRSSI）
            
        Returns:
            推定距離（メートル）
        """
        if rssi == 0:
            return self.max_distance
            
        # パスロスモデル
        distance = 10 ** ((tx_power - rssi) / (10 * self.path_loss_exponent))
        
        # 最大距離でクリップ
        distance = min(distance, self.max_distance)
        
        return distance
        
    def _clip_to_facility(self, position: Tuple[float, float]) -> Tuple[float, float]:
        """
        位置を施設範囲内にクリップ
        
        Args:
            position: 位置座標
            
        Returns:
            クリップされた位置
        """
        x, y = position
        
        # 施設の寸法を取得
        width = self.layout.get('facility', {}).get('dimensions', {}).get('width', 100)
        height = self.layout.get('facility', {}).get('dimensions', {}).get('height', 50)
        
        # クリップ
        x = max(0, min(x, width))
        y = max(0, min(y, height))
        
        return (x, y)
        
    def get_zone_id(self, position: Tuple[float, float]) -> Optional[str]:
        """
        位置座標からゾーンIDを取得
        
        Args:
            position: 位置座標
            
        Returns:
            ゾーンID
        """
        x, y = position
        
        for zone in self.layout.get('zones', []):
            if self._point_in_polygon(position, zone['polygon']):
                return zone['id']
                
        return None
        
    def _point_in_polygon(self, point: Tuple[float, float], 
                         polygon: List[List[float]]) -> bool:
        """
        点がポリゴン内にあるか判定
        
        Args:
            point: 点の座標
            polygon: ポリゴンの頂点リスト
            
        Returns:
            ポリゴン内にあるかどうか
        """
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
            
        return inside
        
    def smooth_trajectory(self, positions: List[Tuple[float, float]], 
                         window_size: int = 5) -> List[Tuple[float, float]]:
        """
        軌跡をスムージング
        
        Args:
            positions: 位置座標のリスト
            window_size: 移動平均のウィンドウサイズ
            
        Returns:
            スムージングされた軌跡
        """
        if len(positions) < window_size:
            return positions
            
        positions_array = np.array(positions)
        smoothed = []
        
        for i in range(len(positions)):
            start = max(0, i - window_size // 2)
            end = min(len(positions), i + window_size // 2 + 1)
            
            window = positions_array[start:end]
            smoothed_point = np.mean(window, axis=0)
            smoothed.append(tuple(smoothed_point))
            
        return smoothed
        
    def calculate_speed(self, positions: List[Tuple[float, float]], 
                       timestamps: List[float]) -> List[float]:
        """
        移動速度を計算
        
        Args:
            positions: 位置座標のリスト
            timestamps: タイムスタンプのリスト
            
        Returns:
            速度のリスト（m/s）
        """
        if len(positions) < 2:
            return []
            
        speeds = []
        
        for i in range(1, len(positions)):
            # 距離計算
            dist = distance.euclidean(positions[i-1], positions[i])
            
            # 時間差
            time_diff = timestamps[i] - timestamps[i-1]
            
            if time_diff > 0:
                speed = dist / time_diff
                speeds.append(speed)
            else:
                speeds.append(0)
                
        return speeds