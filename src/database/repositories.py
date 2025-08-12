"""データベースリポジトリパターン実装"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    Device, Zone, Receiver, Trajectory, TrajectoryPoint,
    Detection, DwellTime, FlowMatrix, HeatmapData,
    Analytics, Alert, Report
)


class BaseRepository:
    """基底リポジトリクラス"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def commit(self):
        """変更をコミット"""
        await self.session.commit()
        
    async def rollback(self):
        """変更をロールバック"""
        await self.session.rollback()


class DeviceRepository(BaseRepository):
    """デバイスリポジトリ"""
    
    async def create(self, device_data: Dict) -> Device:
        """デバイスを作成"""
        device = Device(**device_data)
        self.session.add(device)
        await self.commit()
        return device
        
    async def get_by_id(self, device_id: str) -> Optional[Device]:
        """IDでデバイスを取得"""
        result = await self.session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalar_one_or_none()
        
    async def get_by_mac(self, mac_address: str) -> Optional[Device]:
        """MACアドレスでデバイスを取得"""
        result = await self.session.execute(
            select(Device).where(Device.mac_address == mac_address)
        )
        return result.scalar_one_or_none()
        
    async def get_active_devices(self, minutes: int = 5) -> List[Device]:
        """アクティブなデバイスを取得"""
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.session.execute(
            select(Device)
            .where(Device.last_seen >= threshold)
            .distinct(Device.device_id)  # device_idで重複除去
            .order_by(Device.device_id, Device.last_seen.desc())
        )
        return result.scalars().all()
        
    async def update_last_seen(self, device_id: str, timestamp: datetime):
        """最終検出時刻を更新"""
        await self.session.execute(
            update(Device)
            .where(Device.device_id == device_id)
            .values(last_seen=timestamp, total_detections=Device.total_detections + 1)
        )
        await self.commit()
        
    async def cleanup_old_devices(self, days: int = 30) -> int:
        """古いデバイスを削除"""
        threshold = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            delete(Device).where(Device.last_seen < threshold)
        )
        await self.commit()
        return result.rowcount
    
    async def get_all(self, skip: int = 0, limit: int = 500) -> List[Device]:
        """全デバイスを取得（ページネーション付き）"""
        result = await self.session.execute(
            select(Device)
            .order_by(Device.last_seen.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def update(self, device_id: str, update_data: Dict):
        """デバイス情報を更新"""
        await self.session.execute(
            update(Device)
            .where(Device.device_id == device_id)
            .values(**update_data)
        )
        await self.commit()
    
    async def delete(self, device_id: str):
        """デバイスを削除"""
        await self.session.execute(
            delete(Device).where(Device.device_id == device_id)
        )
        await self.commit()


class TrajectoryRepository(BaseRepository):
    """軌跡リポジトリ"""
    
    async def create_trajectory(self, trajectory_data: Dict) -> Trajectory:
        """軌跡を作成"""
        trajectory = Trajectory(**trajectory_data)
        self.session.add(trajectory)
        await self.commit()
        return trajectory
        
    async def add_points(self, trajectory_id: str, points: List[Dict]):
        """軌跡ポイントを追加"""
        for point_data in points:
            point = TrajectoryPoint(trajectory_id=trajectory_id, **point_data)
            self.session.add(point)
        await self.commit()
        
    async def get_trajectory(self, trajectory_id: str) -> Optional[Trajectory]:
        """軌跡を取得"""
        result = await self.session.execute(
            select(Trajectory)
            .options(selectinload(Trajectory.points))
            .where(Trajectory.id == trajectory_id)
        )
        return result.scalar_one_or_none()
        
    async def get_device_trajectories(self, device_id: str,
                                     start_time: Optional[datetime] = None,
                                     end_time: Optional[datetime] = None) -> List[Trajectory]:
        """デバイスの軌跡を取得"""
        query = select(Trajectory).where(Trajectory.device_id == device_id)
        
        if start_time:
            query = query.where(Trajectory.start_time >= start_time)
        if end_time:
            query = query.where(Trajectory.end_time <= end_time)
            
        result = await self.session.execute(query.order_by(Trajectory.start_time))
        return result.scalars().all()
        
    async def get_zone_trajectories(self, zone_id: str,
                                   date: datetime) -> List[Trajectory]:
        """ゾーンを通過した軌跡を取得"""
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        result = await self.session.execute(
            select(Trajectory)
            .where(
                and_(
                    Trajectory.zones_visited.contains([zone_id]),
                    Trajectory.start_time >= start_of_day,
                    Trajectory.start_time < end_of_day
                )
            )
        )
        return result.scalars().all()


class DetectionRepository(BaseRepository):
    """検出情報リポジトリ"""
    
    async def create(self, detection_data: Dict) -> Detection:
        """検出情報を作成"""
        detection = Detection(**detection_data)
        self.session.add(detection)
        await self.commit()
        return detection
    
    async def bulk_create(self, detections: List[Dict]):
        """検出情報を一括作成"""
        for detection_data in detections:
            detection = Detection(**detection_data)
            self.session.add(detection)
        await self.commit()
    
    async def get_device_detections(self, device_id: str,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None) -> List[Detection]:
        """デバイスの検出履歴を取得"""
        query = select(Detection).where(Detection.device_id == device_id)
        
        if start_time:
            query = query.where(Detection.timestamp >= start_time)
        if end_time:
            query = query.where(Detection.timestamp <= end_time)
        
        result = await self.session.execute(query.order_by(Detection.timestamp.desc()))
        return result.scalars().all()
    
    async def get_receiver_detections(self, receiver_id: str,
                                     start_time: Optional[datetime] = None,
                                     end_time: Optional[datetime] = None) -> List[Detection]:
        """受信機の検出履歴を取得"""
        query = select(Detection).where(Detection.receiver_id == receiver_id)
        
        if start_time:
            query = query.where(Detection.timestamp >= start_time)
        if end_time:
            query = query.where(Detection.timestamp <= end_time)
        
        result = await self.session.execute(query.order_by(Detection.timestamp.desc()))
        return result.scalars().all()


class DwellTimeRepository(BaseRepository):
    """滞留時間リポジトリ"""
    
    async def create(self, dwell_data: Dict) -> DwellTime:
        """滞留記録を作成"""
        dwell = DwellTime(**dwell_data)
        self.session.add(dwell)
        await self.commit()
        return dwell
    
    async def create_dwell(self, dwell_data: Dict) -> DwellTime:
        """滞留記録を作成"""
        dwell = DwellTime(**dwell_data)
        self.session.add(dwell)
        await self.commit()
        return dwell
        
    async def update_exit_time(self, dwell_id: str, exit_time: datetime):
        """退出時刻を更新"""
        await self.session.execute(
            update(DwellTime)
            .where(DwellTime.id == dwell_id)
            .values(
                exit_time=exit_time,
                duration_seconds=(exit_time - DwellTime.entry_time).total_seconds(),
                is_active=False
            )
        )
        await self.commit()
        
    async def get_active_dwells(self, zone_id: Optional[str] = None) -> List[DwellTime]:
        """アクティブな滞留を取得"""
        query = select(DwellTime).where(DwellTime.is_active == True)
        
        if zone_id:
            query = query.where(DwellTime.zone_id == zone_id)
            
        result = await self.session.execute(query)
        return result.scalars().all()
        
    async def get_zone_dwells(self, zone_id: str,
                             start_time: Optional[datetime] = None,
                             end_time: Optional[datetime] = None) -> List[DwellTime]:
        """ゾーンの滞留記録を取得"""
        query = select(DwellTime).where(DwellTime.zone_id == zone_id)
        
        if start_time:
            query = query.where(DwellTime.entry_time >= start_time)
        if end_time:
            query = query.where(DwellTime.entry_time <= end_time)
            
        result = await self.session.execute(query)
        return result.scalars().all()
        
    async def get_zone_statistics(self, zone_id: str, date: datetime) -> Dict:
        """ゾーンの統計を取得"""
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        result = await self.session.execute(
            select(
                func.count(DwellTime.id).label('total_visits'),
                func.count(func.distinct(DwellTime.device_id)).label('unique_visitors'),
                func.avg(DwellTime.duration_seconds).label('avg_duration'),
                func.max(DwellTime.duration_seconds).label('max_duration'),
                func.min(DwellTime.duration_seconds).label('min_duration')
            )
            .where(
                and_(
                    DwellTime.zone_id == zone_id,
                    DwellTime.entry_time >= start_of_day,
                    DwellTime.entry_time < end_of_day
                )
            )
        )
        
        row = result.one()
        return {
            'total_visits': row.total_visits or 0,
            'unique_visitors': row.unique_visitors or 0,
            'avg_duration': float(row.avg_duration or 0),
            'max_duration': float(row.max_duration or 0),
            'min_duration': float(row.min_duration or 0)
        }
    
    async def get_device_dwells(self, device_id: str,
                               start_time: Optional[datetime] = None,
                               end_time: Optional[datetime] = None) -> List[DwellTime]:
        """デバイスの滞留記録を取得"""
        query = select(DwellTime).where(DwellTime.device_id == device_id)
        
        if start_time:
            query = query.where(DwellTime.entry_time >= start_time)
        if end_time:
            query = query.where(DwellTime.entry_time <= end_time)
            
        result = await self.session.execute(query.order_by(DwellTime.entry_time))
        return result.scalars().all()


class FlowRepository(BaseRepository):
    """フロー分析リポジトリ"""
    
    async def update_flow_matrix(self, from_zone: str, to_zone: str,
                                timestamp: datetime):
        """フロー行列を更新"""
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # 既存レコードを検索
        result = await self.session.execute(
            select(FlowMatrix)
            .where(
                and_(
                    FlowMatrix.from_zone_id == from_zone,
                    FlowMatrix.to_zone_id == to_zone,
                    FlowMatrix.hour == hour,
                    FlowMatrix.day_of_week == day_of_week
                )
            )
        )
        
        flow = result.scalar_one_or_none()
        
        if flow:
            # 既存レコードを更新
            flow.transition_count += 1
            flow.timestamp = timestamp
        else:
            # 新規レコードを作成
            flow = FlowMatrix(
                from_zone_id=from_zone,
                to_zone_id=to_zone,
                timestamp=timestamp,
                hour=hour,
                day_of_week=day_of_week,
                transition_count=1
            )
            self.session.add(flow)
            
        await self.commit()
        
    async def get_flow_matrix(self, date: datetime) -> List[FlowMatrix]:
        """指定日のフロー行列を取得"""
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        result = await self.session.execute(
            select(FlowMatrix)
            .where(
                and_(
                    FlowMatrix.timestamp >= start_of_day,
                    FlowMatrix.timestamp < end_of_day
                )
            )
        )
        return result.scalars().all()
        
    async def get_popular_paths(self, limit: int = 10) -> List[Dict]:
        """人気の移動経路を取得"""
        result = await self.session.execute(
            select(
                FlowMatrix.from_zone_id,
                FlowMatrix.to_zone_id,
                func.sum(FlowMatrix.transition_count).label('total_count')
            )
            .group_by(FlowMatrix.from_zone_id, FlowMatrix.to_zone_id)
            .order_by(func.sum(FlowMatrix.transition_count).desc())
            .limit(limit)
        )
        
        return [
            {
                'from_zone': row.from_zone_id,
                'to_zone': row.to_zone_id,
                'count': row.total_count
            }
            for row in result
        ]


class HeatmapRepository(BaseRepository):
    """ヒートマップリポジトリ"""
    
    async def save_heatmap_data(self, heatmap_data: List[Dict]):
        """ヒートマップデータを保存"""
        for data in heatmap_data:
            heatmap = HeatmapData(**data)
            self.session.add(heatmap)
        await self.commit()
        
    async def get_heatmap_data(self, timestamp: datetime,
                              time_window: int = 5) -> List[HeatmapData]:
        """ヒートマップデータを取得"""
        start_time = timestamp - timedelta(minutes=time_window)
        
        result = await self.session.execute(
            select(HeatmapData)
            .where(
                and_(
                    HeatmapData.timestamp >= start_time,
                    HeatmapData.timestamp <= timestamp
                )
            )
            .order_by(HeatmapData.timestamp.desc())
        )
        return result.scalars().all()
        
    async def get_zone_density(self, zone_id: str,
                              timestamp: datetime) -> float:
        """ゾーンの密度を取得"""
        result = await self.session.execute(
            select(func.avg(HeatmapData.density))
            .where(
                and_(
                    HeatmapData.zone_id == zone_id,
                    HeatmapData.timestamp == timestamp
                )
            )
        )
        return float(result.scalar() or 0)


class AlertRepository(BaseRepository):
    """アラートリポジトリ"""
    
    async def create_alert(self, alert_data: Dict) -> Alert:
        """アラートを作成"""
        alert = Alert(**alert_data)
        self.session.add(alert)
        await self.commit()
        return alert
        
    async def get_unresolved_alerts(self) -> List[Alert]:
        """未解決のアラートを取得"""
        result = await self.session.execute(
            select(Alert)
            .where(Alert.is_resolved == False)
            .order_by(Alert.timestamp.desc())
        )
        return result.scalars().all()
        
    async def resolve_alert(self, alert_id: str):
        """アラートを解決済みにする"""
        await self.session.execute(
            update(Alert)
            .where(Alert.id == alert_id)
            .values(is_resolved=True, resolved_at=datetime.utcnow())
        )
        await self.commit()
        
    async def get_recent_alerts(self, hours: int = 24) -> List[Alert]:
        """最近のアラートを取得"""
        threshold = datetime.utcnow() - timedelta(hours=hours)
        
        result = await self.session.execute(
            select(Alert)
            .where(Alert.timestamp >= threshold)
            .order_by(Alert.timestamp.desc())
        )
        return result.scalars().all()


class AnalyticsRepository(BaseRepository):
    """分析リポジトリ"""
    
    async def save_analytics(self, analytics_data: Dict) -> Analytics:
        """分析結果を保存"""
        analytics = Analytics(**analytics_data)
        self.session.add(analytics)
        await self.commit()
        return analytics
        
    async def get_latest_analytics(self) -> Optional[Analytics]:
        """最新の分析結果を取得"""
        result = await self.session.execute(
            select(Analytics)
            .order_by(Analytics.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
        
    async def get_analytics_range(self, start_time: datetime,
                                 end_time: datetime) -> List[Analytics]:
        """期間内の分析結果を取得"""
        result = await self.session.execute(
            select(Analytics)
            .where(
                and_(
                    Analytics.timestamp >= start_time,
                    Analytics.timestamp <= end_time
                )
            )
            .order_by(Analytics.timestamp)
        )
        return result.scalars().all()


class ReportRepository(BaseRepository):
    """レポートリポジトリ"""
    
    async def create_report(self, report_data: Dict) -> Report:
        """レポートを作成"""
        report = Report(**report_data)
        self.session.add(report)
        await self.commit()
        return report
        
    async def get_report(self, report_id: str) -> Optional[Report]:
        """レポートを取得"""
        result = await self.session.execute(
            select(Report).where(Report.id == report_id)
        )
        return result.scalar_one_or_none()
        
    async def get_reports_by_type(self, report_type: str,
                                 limit: int = 10) -> List[Report]:
        """タイプ別にレポートを取得"""
        result = await self.session.execute(
            select(Report)
            .where(Report.report_type == report_type)
            .order_by(Report.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
        
    async def get_recent_reports(self, days: int = 7) -> List[Report]:
        """最近のレポートを取得"""
        threshold = datetime.utcnow() - timedelta(days=days)
        
        result = await self.session.execute(
            select(Report)
            .where(Report.created_at >= threshold)
            .order_by(Report.created_at.desc())
        )
        return result.scalars().all()