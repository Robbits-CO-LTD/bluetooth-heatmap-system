"""API依存関数"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import DatabaseConnection
from src.database.repositories import (
    DeviceRepository,
    TrajectoryRepository,
    DwellTimeRepository,
    FlowRepository,
    HeatmapRepository,
    AnalyticsRepository,
    AlertRepository,
    ReportRepository
)


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """データベースセッションを取得"""
    try:
        db_conn: DatabaseConnection = request.app.state.db
        async with db_conn.get_session() as session:
            yield session
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")


def get_device_repository(
    session: AsyncSession = Depends(get_db_session)
) -> DeviceRepository:
    """デバイスリポジトリを取得"""
    return DeviceRepository(session)


def get_trajectory_repository(
    session: AsyncSession = Depends(get_db_session)
) -> TrajectoryRepository:
    """軌跡リポジトリを取得"""
    return TrajectoryRepository(session)


def get_dwell_time_repository(
    session: AsyncSession = Depends(get_db_session)
) -> DwellTimeRepository:
    """滞留時間リポジトリを取得"""
    return DwellTimeRepository(session)


def get_flow_repository(
    session: AsyncSession = Depends(get_db_session)
) -> FlowRepository:
    """フローリポジトリを取得"""
    return FlowRepository(session)


def get_heatmap_repository(
    session: AsyncSession = Depends(get_db_session)
) -> HeatmapRepository:
    """ヒートマップリポジトリを取得"""
    return HeatmapRepository(session)


def get_analytics_repository(
    session: AsyncSession = Depends(get_db_session)
) -> AnalyticsRepository:
    """分析リポジトリを取得"""
    return AnalyticsRepository(session)


def get_alert_repository(
    session: AsyncSession = Depends(get_db_session)
) -> AlertRepository:
    """アラートリポジトリを取得"""
    return AlertRepository(session)


def get_report_repository(
    session: AsyncSession = Depends(get_db_session)
) -> ReportRepository:
    """レポートリポジトリを取得"""
    return ReportRepository(session)


async def get_config(request: Request) -> dict:
    """設定を取得"""
    return request.app.state.config


async def get_ws_manager(request: Request):
    """WebSocket接続マネージャーを取得"""
    return request.app.state.ws_manager