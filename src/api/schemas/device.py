"""デバイス関連のPydanticスキーマ"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class DeviceBase(BaseModel):
    """デバイス基本情報"""
    mac_address: str = Field(..., description="MACアドレス（ハッシュ化済み）")
    device_name: Optional[str] = Field(None, description="デバイス名")
    device_type: Optional[str] = Field(None, description="デバイスタイプ")
    manufacturer: Optional[str] = Field(None, description="製造元")


class DeviceCreate(DeviceBase):
    """デバイス作成用スキーマ"""
    pass


class DeviceUpdate(BaseModel):
    """デバイス更新用スキーマ"""
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    manufacturer: Optional[str] = None


class Device(DeviceBase):
    """デバイス情報スキーマ"""
    id: str = Field(..., description="デバイスID")
    device_id: Optional[str] = Field(None, description="デバイスID（互換性用）")
    first_seen: datetime = Field(..., description="初回検出時刻")
    last_seen: datetime = Field(..., description="最終検出時刻")
    total_duration: Optional[float] = Field(0.0, description="総滞在時間（秒）")
    is_active: Optional[bool] = Field(True, description="アクティブ状態")
    total_detections: Optional[int] = Field(0, description="総検出回数")
    current_x: Optional[float] = Field(None, description="現在のX座標")
    current_y: Optional[float] = Field(None, description="現在のY座標")
    current_zone: Optional[str] = Field(None, description="現在のゾーン")
    signal_strength: Optional[int] = Field(None, description="信号強度")
    
    class Config:
        from_attributes = True


class DeviceWithPosition(Device):
    """位置情報付きデバイススキーマ"""
    current_position: Optional[Dict[str, float]] = Field(None, description="現在位置")
    current_zone: Optional[str] = Field(None, description="現在のゾーン")
    confidence: Optional[float] = Field(None, description="位置精度")


class DeviceTrajectory(BaseModel):
    """デバイス軌跡スキーマ"""
    device_id: str = Field(..., description="デバイスID")
    trajectory_id: str = Field(..., description="軌跡ID")
    start_time: datetime = Field(..., description="開始時刻")
    end_time: Optional[datetime] = Field(None, description="終了時刻")
    points: List[Dict[str, Any]] = Field(..., description="軌跡ポイント")
    total_distance: Optional[float] = Field(None, description="総移動距離")
    average_speed: Optional[float] = Field(None, description="平均速度")
    
    class Config:
        from_attributes = True


class ActiveDevicesSummary(BaseModel):
    """アクティブデバイスサマリー"""
    total_active: int = Field(..., description="アクティブデバイス数")
    zone_distribution: Dict[str, int] = Field(..., description="ゾーン別分布")
    device_types: Dict[str, int] = Field(..., description="デバイスタイプ別分布")
    timestamp: datetime = Field(..., description="タイムスタンプ")