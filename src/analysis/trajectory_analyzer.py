"""軌跡分析モジュール"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrajectoryPoint:
    """軌跡上の1点"""
    device_id: str
    timestamp: datetime
    position: Tuple[float, float]
    zone_id: Optional[str]
    confidence: float
    speed: Optional[float] = None
    direction: Optional[float] = None


@dataclass
class Trajectory:
    """デバイスの軌跡"""
    device_id: str
    start_time: datetime
    end_time: datetime
    points: List[TrajectoryPoint]
    total_distance: float = 0.0
    avg_speed: float = 0.0
    max_speed: float = 0.0
    zones_visited: List[str] = field(default_factory=list)
    dwell_times: Dict[str, float] = field(default_factory=dict)


class TrajectoryAnalyzer:
    """軌跡分析クラス"""
    
    def __init__(self, config: Dict):
        """
        初期化
        
        Args:
            config: 分析設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 軌跡設定
        self.smoothing_window = config.get('smoothing_window', 5)
        self.min_points = config.get('min_points', 10)
        self.interpolation_method = config.get('interpolation_method', 'linear')
        
        # 軌跡データ
        self.trajectories: Dict[str, Trajectory] = {}
        self.active_points: Dict[str, List[TrajectoryPoint]] = defaultdict(list)
        
        # 統計情報
        self.stats = {
            'total_trajectories': 0,
            'avg_trajectory_length': 0.0,
            'avg_speed': 0.0,
            'popular_zones': defaultdict(int)
        }
        
    def add_position(self, device_id: str, position: Tuple[float, float],
                    timestamp: datetime, zone_id: Optional[str] = None,
                    confidence: float = 1.0) -> None:
        """
        新しい位置情報を追加
        
        Args:
            device_id: デバイスID
            position: 位置座標
            timestamp: タイムスタンプ
            zone_id: ゾーンID
            confidence: 信頼度
        """
        # 軌跡ポイントを作成
        point = TrajectoryPoint(
            device_id=device_id,
            timestamp=timestamp,
            position=position,
            zone_id=zone_id,
            confidence=confidence
        )
        
        # アクティブポイントに追加
        self.active_points[device_id].append(point)
        
        # 速度と方向を計算
        if len(self.active_points[device_id]) > 1:
            self._calculate_motion_attributes(device_id)
            
        # スムージング処理
        if len(self.active_points[device_id]) >= self.smoothing_window:
            self._smooth_trajectory(device_id)
            
    def _calculate_motion_attributes(self, device_id: str) -> None:
        """
        移動属性（速度、方向）を計算
        
        Args:
            device_id: デバイスID
        """
        points = self.active_points[device_id]
        if len(points) < 2:
            return
            
        # 最新2点から計算
        p1 = points[-2]
        p2 = points[-1]
        
        # 距離計算
        dx = p2.position[0] - p1.position[0]
        dy = p2.position[1] - p1.position[1]
        distance = np.sqrt(dx**2 + dy**2)
        
        # 時間差
        time_diff = (p2.timestamp - p1.timestamp).total_seconds()
        
        if time_diff > 0:
            # 速度
            p2.speed = distance / time_diff
            
            # 方向（ラジアン）
            p2.direction = np.arctan2(dy, dx)
            
    def _smooth_trajectory(self, device_id: str) -> None:
        """
        軌跡をスムージング
        
        Args:
            device_id: デバイスID
        """
        points = self.active_points[device_id]
        
        if len(points) < self.smoothing_window:
            return
            
        # 最新のウィンドウサイズ分の点を取得
        window_points = points[-self.smoothing_window:]
        
        # 位置の移動平均
        positions = np.array([p.position for p in window_points])
        smoothed_position = np.mean(positions, axis=0)
        
        # 最新点の位置を更新
        points[-1].position = tuple(smoothed_position)
        
    def finalize_trajectory(self, device_id: str) -> Optional[Trajectory]:
        """
        軌跡を確定
        
        Args:
            device_id: デバイスID
            
        Returns:
            確定した軌跡
        """
        if device_id not in self.active_points:
            return None
            
        points = self.active_points[device_id]
        
        if len(points) < self.min_points:
            self.logger.debug(f"Not enough points for trajectory: {len(points)} < {self.min_points}")
            return None
            
        # 軌跡オブジェクトを作成
        trajectory = Trajectory(
            device_id=device_id,
            start_time=points[0].timestamp,
            end_time=points[-1].timestamp,
            points=points
        )
        
        # 統計情報を計算
        self._calculate_trajectory_stats(trajectory)
        
        # 保存
        self.trajectories[device_id] = trajectory
        
        # アクティブポイントをクリア
        del self.active_points[device_id]
        
        # 全体統計を更新
        self._update_global_stats()
        
        return trajectory
        
    def _calculate_trajectory_stats(self, trajectory: Trajectory) -> None:
        """
        軌跡の統計情報を計算
        
        Args:
            trajectory: 軌跡オブジェクト
        """
        points = trajectory.points
        
        # 総移動距離
        total_distance = 0.0
        speeds = []
        
        for i in range(1, len(points)):
            p1 = points[i-1]
            p2 = points[i]
            
            # 距離
            dx = p2.position[0] - p1.position[0]
            dy = p2.position[1] - p1.position[1]
            distance = np.sqrt(dx**2 + dy**2)
            total_distance += distance
            
            # 速度
            if p2.speed is not None:
                speeds.append(p2.speed)
                
        trajectory.total_distance = total_distance
        
        # 速度統計
        if speeds:
            trajectory.avg_speed = np.mean(speeds)
            trajectory.max_speed = np.max(speeds)
            
        # 訪問ゾーン
        zones_visited = []
        current_zone = None
        zone_entry_time = None
        
        for point in points:
            if point.zone_id != current_zone:
                # ゾーン変更
                if current_zone and zone_entry_time:
                    # 前のゾーンの滞留時間を記録
                    dwell_time = (point.timestamp - zone_entry_time).total_seconds()
                    trajectory.dwell_times[current_zone] = trajectory.dwell_times.get(current_zone, 0) + dwell_time
                    
                if point.zone_id and point.zone_id not in zones_visited:
                    zones_visited.append(point.zone_id)
                    
                current_zone = point.zone_id
                zone_entry_time = point.timestamp
                
        # 最後のゾーンの滞留時間
        if current_zone and zone_entry_time:
            dwell_time = (points[-1].timestamp - zone_entry_time).total_seconds()
            trajectory.dwell_times[current_zone] = trajectory.dwell_times.get(current_zone, 0) + dwell_time
            
        trajectory.zones_visited = zones_visited
        
    def _update_global_stats(self) -> None:
        """全体統計を更新"""
        if not self.trajectories:
            return
            
        # 軌跡数
        self.stats['total_trajectories'] = len(self.trajectories)
        
        # 平均軌跡長
        distances = [t.total_distance for t in self.trajectories.values()]
        self.stats['avg_trajectory_length'] = np.mean(distances)
        
        # 平均速度
        speeds = [t.avg_speed for t in self.trajectories.values() if t.avg_speed > 0]
        if speeds:
            self.stats['avg_speed'] = np.mean(speeds)
            
        # 人気ゾーン
        zone_visits = defaultdict(int)
        for trajectory in self.trajectories.values():
            for zone in trajectory.zones_visited:
                zone_visits[zone] += 1
                
        self.stats['popular_zones'] = dict(zone_visits)
        
    def get_trajectory(self, device_id: str) -> Optional[Trajectory]:
        """
        デバイスの軌跡を取得
        
        Args:
            device_id: デバイスID
            
        Returns:
            軌跡オブジェクト
        """
        return self.trajectories.get(device_id)
        
    def get_trajectories_by_zone(self, zone_id: str) -> List[Trajectory]:
        """
        特定ゾーンを通過した軌跡を取得
        
        Args:
            zone_id: ゾーンID
            
        Returns:
            軌跡リスト
        """
        trajectories = []
        
        for trajectory in self.trajectories.values():
            if zone_id in trajectory.zones_visited:
                trajectories.append(trajectory)
                
        return trajectories
        
    def get_trajectories_in_timerange(self, start_time: datetime, 
                                     end_time: datetime) -> List[Trajectory]:
        """
        時間範囲内の軌跡を取得
        
        Args:
            start_time: 開始時刻
            end_time: 終了時刻
            
        Returns:
            軌跡リスト
        """
        trajectories = []
        
        for trajectory in self.trajectories.values():
            # 時間範囲の重なりをチェック
            if trajectory.start_time <= end_time and trajectory.end_time >= start_time:
                trajectories.append(trajectory)
                
        return trajectories
        
    def calculate_similarity(self, traj1: Trajectory, traj2: Trajectory) -> float:
        """
        2つの軌跡の類似度を計算
        
        Args:
            traj1: 軌跡1
            traj2: 軌跡2
            
        Returns:
            類似度スコア（0-1）
        """
        # Dynamic Time Warping (DTW) を使用
        points1 = np.array([p.position for p in traj1.points])
        points2 = np.array([p.position for p in traj2.points])
        
        # DTW距離を計算
        dtw_distance = self._dtw_distance(points1, points2)
        
        # 正規化して類似度に変換
        max_distance = max(traj1.total_distance, traj2.total_distance)
        if max_distance > 0:
            similarity = 1.0 - min(dtw_distance / max_distance, 1.0)
        else:
            similarity = 0.0
            
        return similarity
        
    def _dtw_distance(self, seq1: np.ndarray, seq2: np.ndarray) -> float:
        """
        Dynamic Time Warpingによる距離計算
        
        Args:
            seq1: シーケンス1
            seq2: シーケンス2
            
        Returns:
            DTW距離
        """
        n, m = len(seq1), len(seq2)
        dtw = np.full((n + 1, m + 1), np.inf)
        dtw[0, 0] = 0
        
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = np.linalg.norm(seq1[i-1] - seq2[j-1])
                dtw[i, j] = cost + min(
                    dtw[i-1, j],    # 挿入
                    dtw[i, j-1],    # 削除
                    dtw[i-1, j-1]   # 置換
                )
                
        return dtw[n, m]
        
    def find_common_patterns(self, min_support: int = 5) -> List[Dict]:
        """
        共通の移動パターンを検出
        
        Args:
            min_support: 最小サポート数
            
        Returns:
            パターンリスト
        """
        # ゾーンシーケンスを抽出
        zone_sequences = []
        for trajectory in self.trajectories.values():
            if len(trajectory.zones_visited) >= 2:
                zone_sequences.append(trajectory.zones_visited)
                
        # 頻出パターンを検出
        patterns = self._find_frequent_sequences(zone_sequences, min_support)
        
        return patterns
        
    def _find_frequent_sequences(self, sequences: List[List[str]], 
                                min_support: int) -> List[Dict]:
        """
        頻出シーケンスを検出
        
        Args:
            sequences: シーケンスリスト
            min_support: 最小サポート数
            
        Returns:
            頻出パターンリスト
        """
        pattern_counts = defaultdict(int)
        
        # 2-gramパターンを数える
        for sequence in sequences:
            for i in range(len(sequence) - 1):
                pattern = tuple(sequence[i:i+2])
                pattern_counts[pattern] += 1
                
        # 3-gramパターンを数える
        for sequence in sequences:
            for i in range(len(sequence) - 2):
                pattern = tuple(sequence[i:i+3])
                pattern_counts[pattern] += 1
                
        # 頻出パターンを抽出
        frequent_patterns = []
        for pattern, count in pattern_counts.items():
            if count >= min_support:
                frequent_patterns.append({
                    'pattern': list(pattern),
                    'count': count,
                    'support': count / len(sequences)
                })
                
        # カウントでソート
        frequent_patterns.sort(key=lambda x: x['count'], reverse=True)
        
        return frequent_patterns
        
    def get_statistics(self) -> Dict:
        """統計情報を取得"""
        return {
            'total_trajectories': self.stats['total_trajectories'],
            'active_trajectories': len(self.active_points),
            'avg_trajectory_length': self.stats['avg_trajectory_length'],
            'avg_speed': self.stats['avg_speed'],
            'popular_zones': self.stats['popular_zones'],
            'timestamp': datetime.now().isoformat()
        }