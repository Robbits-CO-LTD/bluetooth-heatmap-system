"""人流分析モジュール"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from scipy.ndimage import gaussian_filter


@dataclass
class FlowTransition:
    """ゾーン間遷移"""
    from_zone: str
    to_zone: str
    device_id: str
    timestamp: datetime
    duration: float  # 遷移にかかった時間（秒）


@dataclass
class FlowVector:
    """フローベクトル"""
    position: Tuple[float, float]
    direction: Tuple[float, float]
    magnitude: float
    count: int


@dataclass
class FlowPath:
    """人気の移動経路"""
    path: List[str]  # ゾーンIDのリスト
    count: int
    avg_duration: float
    devices: List[str]


class FlowAnalyzer:
    """人流分析クラス"""
    
    def __init__(self, config: Dict, layout: Dict):
        """
        初期化
        
        Args:
            config: 分析設定
            layout: 施設レイアウト
        """
        self.config = config
        self.layout = layout
        self.logger = logging.getLogger(__name__)
        
        # 設定
        self.grid_size = config.get('grid_size', 2.0)
        self.direction_threshold = config.get('direction_threshold', 0.5)
        self.min_flow_count = config.get('min_flow_count', 5)
        
        # 施設寸法
        self.facility_width = layout.get('facility', {}).get('dimensions', {}).get('width', 100)
        self.facility_height = layout.get('facility', {}).get('dimensions', {}).get('height', 50)
        
        # グリッドサイズ
        self.grid_x = int(self.facility_width / self.grid_size)
        self.grid_y = int(self.facility_height / self.grid_size)
        
        # フローデータ
        self.transitions: List[FlowTransition] = []
        self.flow_matrix: Dict[Tuple[str, str], int] = defaultdict(int)
        self.direction_field: np.ndarray = np.zeros((self.grid_y, self.grid_x, 2))
        self.density_field: np.ndarray = np.zeros((self.grid_y, self.grid_x))
        
        # パス分析
        self.device_paths: Dict[str, List[str]] = defaultdict(list)
        self.popular_paths: List[FlowPath] = []
        
        # 遷移時間追跡
        self.device_zone_entry: Dict[str, Dict[str, datetime]] = defaultdict(dict)
        self.transition_durations: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        
    def add_transition(self, device_id: str, from_zone: str, to_zone: str,
                      timestamp: datetime, duration: float = None) -> None:
        """
        ゾーン間遷移を追加
        
        Args:
            device_id: デバイスID
            from_zone: 遷移元ゾーン
            to_zone: 遷移先ゾーン
            timestamp: 遷移時刻
            duration: 遷移時間（省略時は自動計算）
        """
        if from_zone == to_zone:
            return  # 同じゾーンへの遷移は無視
        
        # 遷移時間を自動計算
        if duration is None:
            duration = self._calculate_transition_duration(device_id, from_zone, to_zone, timestamp)
        
        # 遷移記録を作成
        transition = FlowTransition(
            from_zone=from_zone,
            to_zone=to_zone,
            device_id=device_id,
            timestamp=timestamp,
            duration=duration
        )
        
        self.transitions.append(transition)
        
        # フロー行列を更新
        self.flow_matrix[(from_zone, to_zone)] += 1
        
        # 遷移時間を記録
        self.transition_durations[(from_zone, to_zone)].append(duration)
        
        # デバイスパスを更新
        if device_id not in self.device_paths or self.device_paths[device_id][-1] != from_zone:
            self.device_paths[device_id].append(from_zone)
        self.device_paths[device_id].append(to_zone)
        
        self.logger.debug(f"Flow transition: {from_zone} -> {to_zone} (device: {device_id}, duration: {duration:.1f}s)")
    
    def update_device_zone(self, device_id: str, zone_id: str, timestamp: datetime) -> None:
        """
        デバイスのゾーン位置を更新（遷移時間追跡用）
        
        Args:
            device_id: デバイスID
            zone_id: 現在のゾーンID
            timestamp: タイムスタンプ
        """
        if zone_id:
            # 前のゾーンを取得
            device_zones = self.device_zone_entry[device_id]
            previous_zone = None
            previous_entry_time = None
            
            # 現在のゾーンから退出したゾーンを特定
            for zone, entry_time in list(device_zones.items()):
                if zone != zone_id:
                    previous_zone = zone
                    previous_entry_time = entry_time
                    # 退出したゾーンを削除
                    del device_zones[zone]
                    break
            
            # 新しいゾーンに入った時刻を記録
            device_zones[zone_id] = timestamp
            
            # ゾーン遷移があった場合
            if previous_zone and previous_zone != zone_id:
                # 遷移時間を計算（前のゾーンから出て新しいゾーンに入るまでの時間）
                transition_duration = (timestamp - previous_entry_time).total_seconds()
                
                # 遷移を記録
                self.add_transition(
                    device_id=device_id,
                    from_zone=previous_zone,
                    to_zone=zone_id,
                    timestamp=timestamp,
                    duration=transition_duration
                )
    
    def _calculate_transition_duration(self, device_id: str, from_zone: str, 
                                      to_zone: str, timestamp: datetime) -> float:
        """
        遷移時間を計算
        
        Args:
            device_id: デバイスID
            from_zone: 遷移元ゾーン
            to_zone: 遷移先ゾーン
            timestamp: 遷移時刻
            
        Returns:
            遷移時間（秒）
        """
        # デバイスのゾーン入場時刻履歴から計算
        device_zones = self.device_zone_entry.get(device_id, {})
        
        if from_zone in device_zones:
            # 前のゾーンに入った時刻から現在までの時間
            duration = (timestamp - device_zones[from_zone]).total_seconds()
            return max(0.0, duration)  # 負の値を防ぐ
        else:
            # デフォルト値（履歴がない場合）
            return 5.0  # デフォルト5秒
        
    def update_direction_field(self, trajectories: Dict[str, List[Tuple[datetime, Tuple[float, float]]]]) -> None:
        """
        軌跡データから方向場を更新
        
        Args:
            trajectories: デバイスID -> 軌跡ポイントの辞書
        """
        # フィールドをリセット
        self.direction_field = np.zeros((self.grid_y, self.grid_x, 2))
        count_field = np.zeros((self.grid_y, self.grid_x))
        
        for device_id, trajectory in trajectories.items():
            if len(trajectory) < 2:
                continue
                
            for i in range(len(trajectory) - 1):
                t1, p1 = trajectory[i]
                t2, p2 = trajectory[i + 1]
                
                # 移動ベクトル
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                
                # グリッドインデックス
                grid_j = int(p1[0] / self.grid_size)
                grid_i = int(p1[1] / self.grid_size)
                
                if 0 <= grid_i < self.grid_y and 0 <= grid_j < self.grid_x:
                    self.direction_field[grid_i, grid_j, 0] += dx
                    self.direction_field[grid_i, grid_j, 1] += dy
                    count_field[grid_i, grid_j] += 1
                    
        # 正規化
        for i in range(self.grid_y):
            for j in range(self.grid_x):
                if count_field[i, j] > 0:
                    self.direction_field[i, j] /= count_field[i, j]
                    
                    # ベクトルの大きさを正規化
                    magnitude = np.linalg.norm(self.direction_field[i, j])
                    if magnitude > 0:
                        self.direction_field[i, j] /= magnitude
                        
    def update_density_field(self, positions: List[Tuple[float, float]]) -> None:
        """
        現在位置から密度場を更新
        
        Args:
            positions: デバイス位置のリスト
        """
        # フィールドをリセット
        self.density_field = np.zeros((self.grid_y, self.grid_x))
        
        for x, y in positions:
            grid_j = int(x / self.grid_size)
            grid_i = int(y / self.grid_size)
            
            if 0 <= grid_i < self.grid_y and 0 <= grid_j < self.grid_x:
                self.density_field[grid_i, grid_j] += 1
                
        # ガウシアンフィルタでスムージング
        self.density_field = gaussian_filter(self.density_field, sigma=1.0)
        
    def get_flow_matrix(self, normalize: bool = False) -> np.ndarray:
        """
        フロー行列を取得
        
        Args:
            normalize: 正規化するか
            
        Returns:
            フロー行列
        """
        # ゾーンリストを作成
        zones = list(set([z['id'] for z in self.layout.get('zones', [])]))
        n_zones = len(zones)
        
        # 行列を作成
        matrix = np.zeros((n_zones, n_zones))
        
        for (from_zone, to_zone), count in self.flow_matrix.items():
            if from_zone in zones and to_zone in zones:
                i = zones.index(from_zone)
                j = zones.index(to_zone)
                matrix[i, j] = count
                
        if normalize:
            # 行ごとに正規化
            row_sums = matrix.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1  # 0除算を避ける
            matrix = matrix / row_sums
            
        return matrix
        
    def get_popular_paths(self, top_n: int = 10) -> List[FlowPath]:
        """
        人気の移動経路を取得
        
        Args:
            top_n: 上位N件
            
        Returns:
            人気経路リスト
        """
        path_counts = defaultdict(lambda: {'count': 0, 'durations': [], 'devices': set()})
        
        # パスを集計
        for device_id, path in self.device_paths.items():
            if len(path) < 2:
                continue
                
            # 2-gram, 3-gram, 4-gramパスを抽出
            for length in [2, 3, 4]:
                for i in range(len(path) - length + 1):
                    sub_path = tuple(path[i:i+length])
                    path_counts[sub_path]['count'] += 1
                    path_counts[sub_path]['devices'].add(device_id)
                    
        # FlowPathオブジェクトに変換
        flow_paths = []
        for path, data in path_counts.items():
            if data['count'] >= self.min_flow_count:
                flow_path = FlowPath(
                    path=list(path),
                    count=data['count'],
                    avg_duration=0.0,  # TODO: 実際の遷移時間から計算
                    devices=list(data['devices'])
                )
                flow_paths.append(flow_path)
                
        # カウントでソート
        flow_paths.sort(key=lambda p: p.count, reverse=True)
        
        self.popular_paths = flow_paths[:top_n]
        return self.popular_paths
        
    def get_zone_flow_statistics(self, zone_id: str) -> Dict:
        """
        ゾーンのフロー統計を取得
        
        Args:
            zone_id: ゾーンID
            
        Returns:
            フロー統計
        """
        inflow = 0
        outflow = 0
        top_sources = defaultdict(int)
        top_destinations = defaultdict(int)
        
        for (from_zone, to_zone), count in self.flow_matrix.items():
            if to_zone == zone_id:
                inflow += count
                top_sources[from_zone] += count
            if from_zone == zone_id:
                outflow += count
                top_destinations[to_zone] += count
                
        # 上位ソース/デスティネーションを取得
        top_sources = sorted(top_sources.items(), key=lambda x: x[1], reverse=True)[:5]
        top_destinations = sorted(top_destinations.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'zone_id': zone_id,
            'total_inflow': inflow,
            'total_outflow': outflow,
            'net_flow': inflow - outflow,
            'top_sources': top_sources,
            'top_destinations': top_destinations
        }
        
    def get_bottlenecks(self, threshold_percentile: float = 90) -> List[Dict]:
        """
        ボトルネック（混雑箇所）を検出
        
        Args:
            threshold_percentile: 閾値パーセンタイル
            
        Returns:
            ボトルネック情報のリスト
        """
        bottlenecks = []
        
        # 密度フィールドの閾値を計算
        flat_density = self.density_field.flatten()
        threshold = np.percentile(flat_density, threshold_percentile)
        
        # 高密度エリアを検出
        high_density_mask = self.density_field > threshold
        
        for i in range(self.grid_y):
            for j in range(self.grid_x):
                if high_density_mask[i, j]:
                    # グリッド座標を実座標に変換
                    x = (j + 0.5) * self.grid_size
                    y = (i + 0.5) * self.grid_size
                    
                    bottlenecks.append({
                        'position': (x, y),
                        'grid_position': (i, j),
                        'density': self.density_field[i, j],
                        'flow_direction': self.direction_field[i, j].tolist()
                    })
                    
        # 密度でソート
        bottlenecks.sort(key=lambda b: b['density'], reverse=True)
        
        return bottlenecks
        
    def predict_next_zone(self, current_zone: str, n_predictions: int = 3) -> List[Tuple[str, float]]:
        """
        次の訪問ゾーンを予測
        
        Args:
            current_zone: 現在のゾーン
            n_predictions: 予測数
            
        Returns:
            (ゾーンID, 確率)のリスト
        """
        predictions = []
        
        # 現在のゾーンからの遷移を取得
        transitions_from_zone = {}
        total_transitions = 0
        
        for (from_zone, to_zone), count in self.flow_matrix.items():
            if from_zone == current_zone:
                transitions_from_zone[to_zone] = count
                total_transitions += count
                
        if total_transitions == 0:
            return []
            
        # 確率を計算
        for zone, count in transitions_from_zone.items():
            probability = count / total_transitions
            predictions.append((zone, probability))
            
        # 確率でソート
        predictions.sort(key=lambda p: p[1], reverse=True)
        
        return predictions[:n_predictions]
        
    def get_flow_vectors(self, grid_spacing: int = 2) -> List[FlowVector]:
        """
        フローベクトルを取得（可視化用）
        
        Args:
            grid_spacing: グリッド間隔
            
        Returns:
            フローベクトルのリスト
        """
        vectors = []
        
        for i in range(0, self.grid_y, grid_spacing):
            for j in range(0, self.grid_x, grid_spacing):
                direction = self.direction_field[i, j]
                magnitude = np.linalg.norm(direction)
                
                if magnitude > self.direction_threshold:
                    # グリッド座標を実座標に変換
                    x = (j + 0.5) * self.grid_size
                    y = (i + 0.5) * self.grid_size
                    
                    vector = FlowVector(
                        position=(x, y),
                        direction=tuple(direction),
                        magnitude=magnitude,
                        count=int(self.density_field[i, j])
                    )
                    vectors.append(vector)
                    
        return vectors
        
    def get_statistics(self) -> Dict:
        """統計情報を取得"""
        total_transitions = len(self.transitions)
        unique_paths = len(self.device_paths)
        
        # 最も混雑した遷移
        if self.flow_matrix:
            busiest_transition = max(self.flow_matrix.items(), key=lambda x: x[1])
            busiest = {
                'from': busiest_transition[0][0],
                'to': busiest_transition[0][1],
                'count': busiest_transition[1]
            }
        else:
            busiest = None
            
        return {
            'total_transitions': total_transitions,
            'unique_paths': unique_paths,
            'unique_transitions': len(self.flow_matrix),
            'busiest_transition': busiest,
            'avg_flow_per_transition': np.mean(list(self.flow_matrix.values())) if self.flow_matrix else 0,
            'max_density': np.max(self.density_field),
            'avg_density': np.mean(self.density_field),
            'timestamp': datetime.now().isoformat()
        }