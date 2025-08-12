"""滞留時間分析モジュール"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class DwellRecord:
    """滞留記録"""
    device_id: str
    zone_id: str
    entry_time: datetime
    exit_time: Optional[datetime]
    duration: float  # 秒
    is_active: bool = True


@dataclass 
class ZoneStatistics:
    """ゾーン統計情報"""
    zone_id: str
    total_visits: int
    unique_visitors: int
    avg_duration: float
    median_duration: float
    max_duration: float
    min_duration: float
    std_duration: float
    current_occupancy: int
    peak_occupancy: int
    peak_time: Optional[datetime]


class DwellTimeAnalyzer:
    """滞留時間分析クラス"""
    
    def __init__(self, config: Dict):
        """
        初期化
        
        Args:
            config: 分析設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 設定
        self.min_dwell_time = config.get('min_duration', 10.0)  # 最小滞留時間（秒）
        self.zones_of_interest = config.get('zones_of_interest', [])
        
        # 滞留記録
        self.dwell_records: Dict[str, List[DwellRecord]] = defaultdict(list)  # zone_id -> records
        self.active_dwells: Dict[str, DwellRecord] = {}  # device_id -> active record
        
        # ゾーン占有状況
        self.zone_occupancy: Dict[str, int] = defaultdict(int)
        self.zone_peak_occupancy: Dict[str, Tuple[int, datetime]] = {}
        
        # 統計キャッシュ
        self._stats_cache: Dict[str, ZoneStatistics] = {}
        self._cache_timestamp: Optional[datetime] = None
        
    def enter_zone(self, device_id: str, zone_id: str, timestamp: datetime) -> None:
        """
        ゾーンへの入場を記録
        
        Args:
            device_id: デバイスID
            zone_id: ゾーンID
            timestamp: 入場時刻
        """
        # 既存のアクティブ滞留を終了
        if device_id in self.active_dwells:
            self.exit_zone(device_id, self.active_dwells[device_id].zone_id, timestamp)
            
        # 新しい滞留記録を作成
        record = DwellRecord(
            device_id=device_id,
            zone_id=zone_id,
            entry_time=timestamp,
            exit_time=None,
            duration=0.0,
            is_active=True
        )
        
        self.active_dwells[device_id] = record
        
        # 占有状況を更新
        self.zone_occupancy[zone_id] += 1
        
        # ピーク占有を更新
        current_occupancy = self.zone_occupancy[zone_id]
        if zone_id not in self.zone_peak_occupancy or current_occupancy > self.zone_peak_occupancy[zone_id][0]:
            self.zone_peak_occupancy[zone_id] = (current_occupancy, timestamp)
            
        self.logger.debug(f"Device {device_id} entered zone {zone_id}")
        
    def exit_zone(self, device_id: str, zone_id: str, timestamp: datetime) -> Optional[DwellRecord]:
        """
        ゾーンからの退出を記録
        
        Args:
            device_id: デバイスID
            zone_id: ゾーンID
            timestamp: 退出時刻
            
        Returns:
            完了した滞留記録
        """
        if device_id not in self.active_dwells:
            return None
            
        record = self.active_dwells[device_id]
        
        # ゾーンが一致しない場合は警告
        if record.zone_id != zone_id:
            self.logger.warning(f"Zone mismatch for device {device_id}: expected {record.zone_id}, got {zone_id}")
            
        # 滞留時間を計算
        record.exit_time = timestamp
        record.duration = (timestamp - record.entry_time).total_seconds()
        record.is_active = False
        
        # 最小滞留時間をチェック
        if record.duration >= self.min_dwell_time:
            self.dwell_records[record.zone_id].append(record)
            self.logger.debug(f"Device {device_id} exited zone {zone_id}, duration: {record.duration:.1f}s")
        else:
            self.logger.debug(f"Device {device_id} dwell time too short: {record.duration:.1f}s < {self.min_dwell_time}s")
            
        # アクティブ滞留から削除
        del self.active_dwells[device_id]
        
        # 占有状況を更新
        self.zone_occupancy[zone_id] = max(0, self.zone_occupancy[zone_id] - 1)
        
        # キャッシュを無効化
        self._invalidate_cache()
        
        return record if record.duration >= self.min_dwell_time else None
        
    def update_position(self, device_id: str, zone_id: Optional[str], timestamp: datetime) -> None:
        """
        デバイスの位置更新を処理
        
        Args:
            device_id: デバイスID
            zone_id: 現在のゾーンID（Noneの場合はゾーン外）
            timestamp: タイムスタンプ
        """
        if device_id in self.active_dwells:
            current_zone = self.active_dwells[device_id].zone_id
            
            if zone_id != current_zone:
                # ゾーンが変わった
                self.exit_zone(device_id, current_zone, timestamp)
                
                if zone_id:
                    self.enter_zone(device_id, zone_id, timestamp)
        elif zone_id:
            # 新規入場
            self.enter_zone(device_id, zone_id, timestamp)
            
    def get_zone_statistics(self, zone_id: str, 
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None) -> Optional[ZoneStatistics]:
        """
        ゾーンの統計情報を取得
        
        Args:
            zone_id: ゾーンID
            start_time: 開始時刻
            end_time: 終了時刻
            
        Returns:
            ゾーン統計情報
        """
        # キャッシュチェック
        if not start_time and not end_time and zone_id in self._stats_cache:
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).seconds < 60:
                return self._stats_cache[zone_id]
                
        # 該当する記録を取得
        records = self.dwell_records.get(zone_id, [])
        
        if start_time or end_time:
            filtered_records = []
            for record in records:
                if start_time and record.entry_time < start_time:
                    continue
                if end_time and record.entry_time > end_time:
                    continue
                filtered_records.append(record)
            records = filtered_records
            
        if not records:
            return None
            
        # 統計計算
        durations = [r.duration for r in records]
        unique_devices = len(set(r.device_id for r in records))
        
        stats = ZoneStatistics(
            zone_id=zone_id,
            total_visits=len(records),
            unique_visitors=unique_devices,
            avg_duration=np.mean(durations),
            median_duration=np.median(durations),
            max_duration=np.max(durations),
            min_duration=np.min(durations),
            std_duration=np.std(durations),
            current_occupancy=self.zone_occupancy.get(zone_id, 0),
            peak_occupancy=self.zone_peak_occupancy.get(zone_id, (0, None))[0],
            peak_time=self.zone_peak_occupancy.get(zone_id, (0, None))[1]
        )
        
        # キャッシュ更新
        if not start_time and not end_time:
            self._stats_cache[zone_id] = stats
            self._cache_timestamp = datetime.now()
            
        return stats
        
    def get_all_zone_statistics(self) -> Dict[str, ZoneStatistics]:
        """
        全ゾーンの統計情報を取得
        
        Returns:
            ゾーンID -> 統計情報の辞書
        """
        stats = {}
        
        for zone_id in self.dwell_records.keys():
            zone_stats = self.get_zone_statistics(zone_id)
            if zone_stats:
                stats[zone_id] = zone_stats
                
        return stats
        
    def get_device_history(self, device_id: str) -> List[DwellRecord]:
        """
        デバイスの滞留履歴を取得
        
        Args:
            device_id: デバイスID
            
        Returns:
            滞留記録リスト
        """
        history = []
        
        for records in self.dwell_records.values():
            for record in records:
                if record.device_id == device_id:
                    history.append(record)
                    
        # 時系列でソート
        history.sort(key=lambda r: r.entry_time)
        
        return history
        
    def get_conversion_rate(self, from_zone: str, to_zone: str,
                          time_window: float = 300.0) -> float:
        """
        ゾーン間のコンバージョン率を計算
        
        Args:
            from_zone: 起点ゾーン
            to_zone: 目的ゾーン
            time_window: 時間ウィンドウ（秒）
            
        Returns:
            コンバージョン率（0-1）
        """
        from_visitors = set()
        converted_visitors = set()
        
        # 起点ゾーンの訪問者を収集
        for record in self.dwell_records.get(from_zone, []):
            from_visitors.add(record.device_id)
            
            # 目的ゾーンへの訪問をチェック
            for to_record in self.dwell_records.get(to_zone, []):
                if to_record.device_id == record.device_id:
                    # 時間ウィンドウ内かチェック
                    if record.exit_time and to_record.entry_time:
                        time_diff = (to_record.entry_time - record.exit_time).total_seconds()
                        if 0 <= time_diff <= time_window:
                            converted_visitors.add(record.device_id)
                            break
                            
        if len(from_visitors) == 0:
            return 0.0
            
        return len(converted_visitors) / len(from_visitors)
        
    def get_hourly_distribution(self, zone_id: str) -> Dict[int, Dict]:
        """
        時間帯別の滞留分布を取得
        
        Args:
            zone_id: ゾーンID
            
        Returns:
            時間帯別の統計情報
        """
        hourly_data = defaultdict(list)
        
        for record in self.dwell_records.get(zone_id, []):
            hour = record.entry_time.hour
            hourly_data[hour].append(record.duration)
            
        distribution = {}
        for hour in range(24):
            if hour in hourly_data:
                durations = hourly_data[hour]
                distribution[hour] = {
                    'count': len(durations),
                    'avg_duration': np.mean(durations),
                    'total_duration': sum(durations)
                }
            else:
                distribution[hour] = {
                    'count': 0,
                    'avg_duration': 0,
                    'total_duration': 0
                }
                
        return distribution
        
    def find_long_dwellers(self, threshold_percentile: float = 90) -> List[DwellRecord]:
        """
        長時間滞留者を検出
        
        Args:
            threshold_percentile: 閾値パーセンタイル
            
        Returns:
            長時間滞留記録のリスト
        """
        all_durations = []
        all_records = []
        
        for records in self.dwell_records.values():
            for record in records:
                all_durations.append(record.duration)
                all_records.append(record)
                
        if not all_durations:
            return []
            
        # 閾値を計算
        threshold = np.percentile(all_durations, threshold_percentile)
        
        # 長時間滞留者を抽出
        long_dwellers = [r for r in all_records if r.duration >= threshold]
        
        # 滞留時間でソート
        long_dwellers.sort(key=lambda r: r.duration, reverse=True)
        
        return long_dwellers
        
    def _invalidate_cache(self) -> None:
        """キャッシュを無効化"""
        self._stats_cache.clear()
        self._cache_timestamp = None
        
    def get_real_time_occupancy(self) -> Dict[str, int]:
        """
        リアルタイム占有状況を取得
        
        Returns:
            ゾーンID -> 占有数の辞書
        """
        return dict(self.zone_occupancy)
        
    def get_statistics(self) -> Dict:
        """全体統計情報を取得"""
        total_records = sum(len(records) for records in self.dwell_records.values())
        all_durations = []
        
        for records in self.dwell_records.values():
            all_durations.extend([r.duration for r in records])
            
        return {
            'total_dwell_records': total_records,
            'active_dwells': len(self.active_dwells),
            'zones_tracked': len(self.dwell_records),
            'avg_dwell_time': np.mean(all_durations) if all_durations else 0,
            'median_dwell_time': np.median(all_durations) if all_durations else 0,
            'total_occupancy': sum(self.zone_occupancy.values()),
            'timestamp': datetime.now().isoformat()
        }