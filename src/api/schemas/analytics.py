"""分析関連のPydanticスキーマ"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta


class DwellTimeAnalysis(BaseModel):
    """滞留時間分析スキーマ"""
    zone_id: str = Field(..., description="ゾーンID")
    zone_name: str = Field(..., description="ゾーン名")
    average_dwell_time: float = Field(..., description="平均滞留時間（秒）")
    median_dwell_time: float = Field(..., description="中央値滞留時間（秒）")
    max_dwell_time: float = Field(..., description="最大滞留時間（秒）")
    min_dwell_time: float = Field(..., description="最小滞留時間（秒）")
    total_visitors: int = Field(..., description="総訪問者数")
    current_occupancy: int = Field(..., description="現在の占有数")
    period: str = Field(..., description="分析期間")
    
    class Config:
        from_attributes = True


class FlowAnalysis(BaseModel):
    """フロー分析スキーマ"""
    from_zone: str = Field(..., description="移動元ゾーン")
    to_zone: str = Field(..., description="移動先ゾーン")
    transition_count: int = Field(..., description="遷移回数")
    average_transition_time: float = Field(..., description="平均遷移時間（秒）")
    percentage: float = Field(..., description="全体に対する割合（%）")
    peak_hour: Optional[int] = Field(None, description="ピーク時間帯")
    
    class Config:
        from_attributes = True


class FlowMatrix(BaseModel):
    """フロー行列スキーマ"""
    zones: List[str] = Field(..., description="ゾーンリスト")
    matrix: List[List[int]] = Field(..., description="遷移行列")
    total_transitions: int = Field(..., description="総遷移回数")
    timestamp: datetime = Field(..., description="タイムスタンプ")


class TrajectoryAnalysis(BaseModel):
    """軌跡分析スキーマ"""
    total_trajectories: int = Field(..., description="総軌跡数")
    average_duration: float = Field(..., description="平均滞在時間（秒）")
    average_distance: float = Field(..., description="平均移動距離（m）")
    popular_paths: List[Dict[str, Any]] = Field(..., description="人気の経路")
    entry_points: Dict[str, int] = Field(..., description="入口別カウント")
    exit_points: Dict[str, int] = Field(..., description="出口別カウント")
    
    class Config:
        from_attributes = True


class PatternDetection(BaseModel):
    """パターン検出スキーマ"""
    pattern_type: str = Field(..., description="パターンタイプ")
    description: str = Field(..., description="パターン説明")
    occurrences: int = Field(..., description="発生回数")
    confidence: float = Field(..., description="信頼度")
    affected_zones: List[str] = Field(..., description="影響を受けるゾーン")
    time_range: Optional[Dict[str, str]] = Field(None, description="時間範囲")
    
    class Config:
        from_attributes = True


class AnomalyAlert(BaseModel):
    """異常検知アラートスキーマ"""
    alert_id: str = Field(..., description="アラートID")
    alert_type: str = Field(..., description="アラートタイプ")
    severity: str = Field(..., description="重要度（low/medium/high/critical）")
    message: str = Field(..., description="アラートメッセージ")
    zone: Optional[str] = Field(None, description="関連ゾーン")
    device_count: Optional[int] = Field(None, description="関連デバイス数")
    timestamp: datetime = Field(..., description="発生時刻")
    resolved: bool = Field(False, description="解決済みフラグ")
    
    class Config:
        from_attributes = True


class Statistics(BaseModel):
    """統計情報スキーマ"""
    period_start: datetime = Field(..., description="期間開始")
    period_end: datetime = Field(..., description="期間終了")
    total_devices: int = Field(..., description="総デバイス数")
    unique_visitors: int = Field(..., description="ユニーク訪問者数")
    average_visit_duration: float = Field(..., description="平均滞在時間（分）")
    peak_hour: int = Field(..., description="ピーク時間帯")
    peak_occupancy: int = Field(..., description="ピーク時占有数")
    busiest_zone: str = Field(..., description="最も混雑したゾーン")
    conversion_rate: Optional[float] = Field(None, description="コンバージョン率")
    
    class Config:
        from_attributes = True