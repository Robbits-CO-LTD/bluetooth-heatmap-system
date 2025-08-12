"""データベースモデル定義"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    ForeignKey, JSON, Index, Text, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
import uuid

Base = declarative_base()


class Device(Base):
    """デバイステーブル"""
    __tablename__ = 'devices'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mac_address = Column(String(17), index=True)  # 匿名化される場合は空
    device_id = Column(String(16), unique=True, index=True)  # 匿名化ID
    device_type = Column(String(50), default='unknown')
    device_name = Column(String(100), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow, index=True)
    last_seen = Column(DateTime, default=datetime.utcnow, index=True)
    is_anonymous = Column(Boolean, default=True)
    total_detections = Column(Integer, default=0)
    current_x = Column(Float, nullable=True)
    current_y = Column(Float, nullable=True)
    current_zone = Column(String(100), nullable=True)
    signal_strength = Column(Integer, nullable=True)
    device_metadata = Column(JSONB, nullable=True)  # metadataは予約語なので変更
    
    # リレーション
    trajectories = relationship("Trajectory", back_populates="device")
    dwell_times = relationship("DwellTime", back_populates="device")
    
    __table_args__ = (
        Index('idx_device_last_seen', 'last_seen'),
        Index('idx_device_type', 'device_type'),
    )


class Zone(Base):
    """ゾーンテーブル"""
    __tablename__ = 'zones'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_code = Column(String(50), unique=True, index=True)
    zone_name = Column(String(100))
    zone_type = Column(String(50))  # entrance, sales_area, cashier, etc.
    floor = Column(Integer, default=1)
    polygon = Column(JSONB)  # ポリゴン座標
    capacity = Column(Integer, nullable=True)
    category = Column(String(50), nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # リレーション
    dwell_times = relationship("DwellTime", back_populates="zone")
    trajectory_points = relationship("TrajectoryPoint", back_populates="zone")


class Receiver(Base):
    """Bluetooth受信機テーブル"""
    __tablename__ = 'receivers'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    receiver_code = Column(String(50), unique=True, index=True)
    receiver_name = Column(String(100))
    position_x = Column(Float)
    position_y = Column(Float)
    floor = Column(Integer, default=1)
    range_meters = Column(Float, default=30.0)
    status = Column(String(20), default='active')  # active, inactive, maintenance
    last_heartbeat = Column(DateTime, nullable=True)
    receiver_info = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # リレーション
    detections = relationship("Detection", back_populates="receiver")


class Trajectory(Base):
    """軌跡テーブル"""
    __tablename__ = 'trajectories'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey('devices.id'), index=True)
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime, index=True)
    total_distance = Column(Float)
    avg_speed = Column(Float)
    max_speed = Column(Float)
    point_count = Column(Integer)
    zones_visited = Column(ARRAY(String))
    trajectory_info = Column(JSONB, nullable=True)
    
    # リレーション
    device = relationship("Device", back_populates="trajectories")
    points = relationship("TrajectoryPoint", back_populates="trajectory", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_trajectory_time_range', 'start_time', 'end_time'),
    )


class TrajectoryPoint(Base):
    """軌跡ポイントテーブル（TimescaleDB用）"""
    __tablename__ = 'trajectory_points'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trajectory_id = Column(String(36), ForeignKey('trajectories.id'), index=True)
    timestamp = Column(DateTime, primary_key=True, index=True)
    x_coordinate = Column(Float)
    y_coordinate = Column(Float)
    zone_id = Column(String(36), ForeignKey('zones.id'), nullable=True, index=True)
    speed = Column(Float, nullable=True)
    direction = Column(Float, nullable=True)  # ラジアン
    confidence = Column(Float, default=1.0)
    rssi = Column(Integer, nullable=True)
    
    # リレーション
    trajectory = relationship("Trajectory", back_populates="points")
    zone = relationship("Zone", back_populates="trajectory_points")
    
    __table_args__ = (
        Index('idx_trajectory_point_timestamp', 'timestamp'),
        Index('idx_trajectory_point_zone', 'zone_id', 'timestamp'),
    )


class Detection(Base):
    """デバイス検出記録テーブル"""
    __tablename__ = 'detections'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey('devices.id'), index=True)
    receiver_id = Column(String(36), ForeignKey('receivers.id'), index=True)
    timestamp = Column(DateTime, index=True)
    rssi = Column(Integer)
    estimated_distance = Column(Float)
    
    # リレーション
    device = relationship("Device")
    receiver = relationship("Receiver", back_populates="detections")
    
    __table_args__ = (
        Index('idx_detection_timestamp', 'timestamp'),
        Index('idx_detection_device_time', 'device_id', 'timestamp'),
    )


class DwellTime(Base):
    """滞留時間テーブル"""
    __tablename__ = 'dwell_times'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey('devices.id'), index=True)
    zone_id = Column(String(36), ForeignKey('zones.id'), index=True)
    entry_time = Column(DateTime, index=True)
    exit_time = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Float)
    is_active = Column(Boolean, default=False)
    
    # リレーション
    device = relationship("Device", back_populates="dwell_times")
    zone = relationship("Zone", back_populates="dwell_times")
    
    __table_args__ = (
        Index('idx_dwell_time_range', 'entry_time', 'exit_time'),
        Index('idx_dwell_zone_time', 'zone_id', 'entry_time'),
    )


class FlowMatrix(Base):
    """フロー行列テーブル"""
    __tablename__ = 'flow_matrix'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_zone_id = Column(String(36), ForeignKey('zones.id'), index=True)
    to_zone_id = Column(String(36), ForeignKey('zones.id'), index=True)
    timestamp = Column(DateTime, index=True)
    hour = Column(Integer, index=True)  # 0-23
    day_of_week = Column(Integer, index=True)  # 0-6
    transition_count = Column(Integer, default=0)
    avg_transition_time = Column(Float, nullable=True)  # avg_duration_secondsから変更
    avg_duration_seconds = Column(Float, nullable=True)
    
    # リレーション
    from_zone = relationship("Zone", foreign_keys=[from_zone_id])
    to_zone = relationship("Zone", foreign_keys=[to_zone_id])
    
    __table_args__ = (
        Index('idx_flow_matrix_zones', 'from_zone_id', 'to_zone_id'),
        Index('idx_flow_matrix_time', 'timestamp', 'hour'),
    )


class HeatmapData(Base):
    """ヒートマップデータテーブル"""
    __tablename__ = 'heatmap_data'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True)
    x = Column(Integer)  # grid_xからxに変更
    y = Column(Integer)  # grid_yからyに変更
    density = Column(Float)
    zone_id = Column(String(36), ForeignKey('zones.id'), nullable=True, index=True)
    
    # リレーション
    zone = relationship("Zone")
    
    __table_args__ = (
        Index('idx_heatmap_timestamp', 'timestamp'),
        Index('idx_heatmap_grid', 'x', 'y', 'timestamp'),  # grid_x, grid_y を x, y に変更
    )


class Analytics(Base):
    """分析統計テーブル"""
    __tablename__ = 'analytics'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(DateTime, index=True)
    hour = Column(Integer, index=True)
    zone_id = Column(String(36), ForeignKey('zones.id'), nullable=True, index=True)
    metric_type = Column(String(50), index=True)  # visitor_count, avg_dwell_time, conversion_rate
    metric_value = Column(Float)
    analytics_data = Column(JSONB, nullable=True)
    
    # リレーション
    zone = relationship("Zone")
    
    __table_args__ = (
        Index('idx_analytics_date_zone', 'date', 'zone_id'),
        Index('idx_analytics_metric', 'metric_type', 'date'),
    )


class Alert(Base):
    """アラートテーブル"""
    __tablename__ = 'alerts'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(String(50), index=True)  # crowding, restricted_area, anomaly
    severity = Column(String(20), index=True)  # low, medium, high, critical
    zone_id = Column(String(36), ForeignKey('zones.id'), nullable=True, index=True)
    device_id = Column(String(36), ForeignKey('devices.id'), nullable=True, index=True)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    message = Column(Text)
    is_resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    alert_details = Column(JSONB, nullable=True)
    
    # リレーション
    zone = relationship("Zone")
    device = relationship("Device")
    
    __table_args__ = (
        Index('idx_alert_unresolved', 'is_resolved', 'timestamp'),
    )


class Report(Base):
    """レポートテーブル"""
    __tablename__ = 'reports'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type = Column(String(50), index=True)  # daily, weekly, monthly
    report_date = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    file_path = Column(String(500))
    file_size = Column(Integer, nullable=True)
    format = Column(String(20))  # pdf, excel, csv
    status = Column(String(20), default='pending')  # pending, generating, completed, failed
    generated_at = Column(DateTime, nullable=True)
    parameters = Column(JSONB, nullable=True)
    report_params = Column(JSONB, nullable=True)
    
    __table_args__ = (
        Index('idx_report_date_type', 'report_date', 'report_type'),
    )