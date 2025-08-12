"""分析関連のAPIルート"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from src.api.schemas.analytics import (
    DwellTimeAnalysis, FlowAnalysis, FlowMatrix,
    TrajectoryAnalysis, PatternDetection, AnomalyAlert,
    Statistics
)
from src.api.dependencies import (
    get_dwell_time_repository,
    get_flow_repository,
    get_trajectory_repository,
    get_analytics_repository,
    get_alert_repository
)
from src.database.repositories import (
    DwellTimeRepository,
    FlowRepository,
    TrajectoryRepository,
    AnalyticsRepository,
    AlertRepository
)


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dwell-time", response_model=List[DwellTimeAnalysis])
async def get_dwell_time_analysis(
    zone_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    dwell_repo: DwellTimeRepository = Depends(get_dwell_time_repository)
):
    """
    滞留時間分析を取得
    
    Args:
        zone_id: ゾーンID（指定しない場合は全ゾーン）
        start_time: 開始時刻
        end_time: 終了時刻
    """
    try:
        # デフォルトの時間範囲（今日）
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = []
        
        if zone_id:
            # 特定ゾーンの統計を取得
            stats = await dwell_repo.get_zone_statistics(zone_id, start_time)
            dwells = await dwell_repo.get_zone_dwells(zone_id, start_time, end_time)
            
            result.append(DwellTimeAnalysis(
                zone_id=zone_id,
                average_dwell_time=stats['avg_duration'],
                max_dwell_time=stats['max_duration'],
                min_dwell_time=stats['min_duration'],
                total_visitors=stats['unique_visitors'],
                total_visits=stats['total_visits'],
                current_occupancy=len([d for d in dwells if d.is_active]),
                timestamp=datetime.now()
            ))
        else:
            # 全ゾーンの統計を取得（簡略化のため空リストを返す）
            # 実際には全ゾーンをループで処理
            pass
        
        return result
    except Exception as e:
        logger.error(f"Error getting dwell time analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flow", response_model=List[FlowAnalysis])
async def get_flow_analysis(
    from_zone: Optional[str] = None,
    to_zone: Optional[str] = None,
    min_count: int = Query(1, ge=1, description="最小遷移回数"),
    flow_repo: FlowRepository = Depends(get_flow_repository)
):
    """
    フロー分析を取得
    
    Args:
        from_zone: 移動元ゾーン
        to_zone: 移動先ゾーン
        min_count: 最小遷移回数
    """
    try:
        # 今日のフローデータを取得
        flows = await flow_repo.get_flow_matrix(datetime.now())
        
        result = []
        for flow in flows:
            # フィルタリング
            if from_zone and flow.from_zone_id != from_zone:
                continue
            if to_zone and flow.to_zone_id != to_zone:
                continue
            if flow.transition_count < min_count:
                continue
            
            result.append(FlowAnalysis(
                from_zone=flow.from_zone_id,
                to_zone=flow.to_zone_id,
                transition_count=flow.transition_count,
                average_transition_time=flow.avg_transition_time or 0.0,
                peak_hour=flow.hour,
                day_of_week=flow.day_of_week
            ))
        
        return result
    except Exception as e:
        logger.error(f"Error getting flow analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flow/matrix", response_model=FlowMatrix)
async def get_flow_matrix(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    flow_repo: FlowRepository = Depends(get_flow_repository)
):
    """
    フロー行列を取得
    
    Args:
        start_time: 開始時刻
        end_time: 終了時刻
    """
    try:
        # デフォルトの時間範囲（今日）
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # フローデータを取得
        flows = await flow_repo.get_flow_matrix(start_time)
        
        # ゾーンリストを作成
        zones = set()
        for flow in flows:
            zones.add(flow.from_zone_id)
            zones.add(flow.to_zone_id)
        zones = sorted(list(zones))
        
        # 行列を作成
        matrix = [[0 for _ in zones] for _ in zones]
        total_transitions = 0
        
        for flow in flows:
            if flow.from_zone_id in zones and flow.to_zone_id in zones:
                i = zones.index(flow.from_zone_id)
                j = zones.index(flow.to_zone_id)
                matrix[i][j] = flow.transition_count
                total_transitions += flow.transition_count
        
        return FlowMatrix(
            zones=zones,
            matrix=matrix,
            total_transitions=total_transitions,
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"Error getting flow matrix: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trajectories", response_model=TrajectoryAnalysis)
async def get_trajectory_analysis(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    zone_filter: Optional[List[str]] = Query(None, description="ゾーンフィルター"),
    trajectory_repo: TrajectoryRepository = Depends(get_trajectory_repository),
    flow_repo: FlowRepository = Depends(get_flow_repository)
):
    """
    軌跡分析を取得
    
    Args:
        start_time: 開始時刻
        end_time: 終了時刻
        zone_filter: 分析対象ゾーン
    """
    try:
        # デフォルトの時間範囲（過去24時間）
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=24)
        
        # 人気の経路を取得
        popular_paths = await flow_repo.get_popular_paths(limit=10)
        
        # エントリー/エグジットポイントを集計（簡略化のため空の辞書を返す）
        entry_points = {}
        exit_points = {}
        
        return TrajectoryAnalysis(
            total_trajectories=len(popular_paths),
            average_duration=0.0,  # TODO: 実際の平均時間を計算
            average_distance=0.0,  # TODO: 実際の平均距離を計算
            popular_paths=[
                {
                    "path": [p['from_zone'], p['to_zone']],
                    "count": p['count']
                }
                for p in popular_paths
            ],
            entry_points=entry_points,
            exit_points=exit_points
        )
    except Exception as e:
        logger.error(f"Error getting trajectory analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns", response_model=List[PatternDetection])
async def get_patterns(
    pattern_type: Optional[str] = None,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="最小信頼度")
):
    """
    検出されたパターンを取得
    
    Args:
        pattern_type: パターンタイプ
        min_confidence: 最小信頼度
    """
    # TODO: 実際のパターン検出データを取得
    return []


@router.get("/anomalies", response_model=List[AnomalyAlert])
async def get_anomalies(
    severity: Optional[str] = Query(None, regex="^(low|medium|high|critical)$"),
    resolved: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """
    異常検知アラートを取得
    
    Args:
        severity: 重要度フィルター
        resolved: 解決済みフィルター
        limit: 取得数上限
    """
    # TODO: 実際の異常検知データを取得
    return []


@router.get("/statistics", response_model=Statistics)
async def get_statistics(
    period: str = Query("today", regex="^(today|yesterday|week|month)$")
):
    """
    統計情報を取得
    
    Args:
        period: 期間（today/yesterday/week/month）
    """
    # TODO: 実際の統計データを取得
    now = datetime.now()
    
    if period == "today":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = now
    elif period == "yesterday":
        yesterday = now - timedelta(days=1)
        period_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == "week":
        period_start = now - timedelta(days=7)
        period_end = now
    else:  # month
        period_start = now - timedelta(days=30)
        period_end = now
    
    return Statistics(
        period_start=period_start,
        period_end=period_end,
        total_devices=0,
        unique_visitors=0,
        average_visit_duration=0.0,
        peak_hour=0,
        peak_occupancy=0,
        busiest_zone="",
        conversion_rate=None
    )


@router.post("/anomalies/{alert_id}/resolve", response_model=AnomalyAlert)
async def resolve_anomaly(alert_id: str):
    """
    異常アラートを解決済みにする
    
    Args:
        alert_id: アラートID
    """
    # TODO: アラートを解決済みに更新
    raise HTTPException(status_code=404, detail="Alert not found")