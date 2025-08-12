"""ヒートマップ関連のPydanticスキーマ"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime


class HeatmapData(BaseModel):
    """ヒートマップデータスキーマ"""
    grid_size: Tuple[int, int] = Field(..., description="グリッドサイズ（幅, 高さ）")
    resolution: float = Field(..., description="解像度（メートル/ピクセル）")
    data: List[List[float]] = Field(..., description="密度データ行列")
    max_value: float = Field(..., description="最大値")
    min_value: float = Field(..., description="最小値")
    timestamp: datetime = Field(..., description="タイムスタンプ")
    
    class Config:
        from_attributes = True


class HeatmapRequest(BaseModel):
    """ヒートマップリクエストスキーマ"""
    time_range: Optional[Dict[str, datetime]] = Field(None, description="時間範囲")
    zone_filter: Optional[List[str]] = Field(None, description="ゾーンフィルター")
    resolution: Optional[float] = Field(1.0, description="解像度（m）")
    smoothing: Optional[bool] = Field(True, description="スムージング適用")
    color_scheme: Optional[str] = Field("hot", description="カラースキーム")


class HeatmapResponse(BaseModel):
    """ヒートマップレスポンススキーマ"""
    data: HeatmapData = Field(..., description="ヒートマップデータ")
    image_url: Optional[str] = Field(None, description="画像URL")
    statistics: Dict[str, Any] = Field(..., description="統計情報")


class ZoneHeatmap(BaseModel):
    """ゾーン別ヒートマップスキーマ"""
    zone_id: str = Field(..., description="ゾーンID")
    zone_name: str = Field(..., description="ゾーン名")
    density: float = Field(..., description="密度")
    occupancy: int = Field(..., description="占有数")
    capacity_percentage: float = Field(..., description="容量使用率（%）")
    color: str = Field(..., description="表示色")
    
    class Config:
        from_attributes = True


class RealtimeHeatmap(BaseModel):
    """リアルタイムヒートマップスキーマ"""
    zones: List[ZoneHeatmap] = Field(..., description="ゾーン別ヒートマップ")
    total_devices: int = Field(..., description="総デバイス数")
    timestamp: datetime = Field(..., description="タイムスタンプ")
    update_interval: int = Field(..., description="更新間隔（秒）")


class HistoricalHeatmap(BaseModel):
    """履歴ヒートマップスキーマ"""
    period: str = Field(..., description="期間（hourly/daily/weekly/monthly）")
    data_points: List[HeatmapData] = Field(..., description="時系列データポイント")
    aggregation_method: str = Field(..., description="集計方法（average/max/sum）")
    comparison: Optional[Dict[str, Any]] = Field(None, description="比較データ")