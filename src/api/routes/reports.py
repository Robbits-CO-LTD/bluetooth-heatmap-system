"""レポート関連のAPIルート"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import os
import logging
from pathlib import Path

from src.api.dependencies import (
    get_device_repository,
    get_dwell_time_repository,
    get_flow_repository,
    get_analytics_repository,
    get_report_repository,
    get_config
)
from src.database.repositories import (
    DeviceRepository,
    DwellTimeRepository,
    FlowRepository,
    AnalyticsRepository,
    ReportRepository
)
from src.api.services.report_generator import ReportGenerator


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
async def get_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    report_type: Optional[str] = None,
    report_repo: ReportRepository = Depends(get_report_repository)
):
    """
    レポート一覧を取得
    
    Args:
        skip: スキップ数
        limit: 取得数
        report_type: レポートタイプフィルター
    """
    try:
        if report_type:
            reports = await report_repo.get_reports_by_type(report_type, limit)
        else:
            reports = await report_repo.get_recent_reports(days=30)
        
        # ページネーション適用
        paginated_reports = reports[skip:skip+limit]
        
        return {
            "reports": [
                {
                    "report_id": r.id,
                    "type": r.report_type,
                    "created_at": r.created_at,
                    "period_start": r.period_start,
                    "period_end": r.period_end,
                    "file_size": r.file_size,
                    "status": r.status
                }
                for r in paginated_reports
            ],
            "total": len(reports),
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error getting reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_report(
    background_tasks: BackgroundTasks,
    report_type: str = Query(..., regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    zones: Optional[List[str]] = Query(None),
    format: str = Query("pdf", regex="^(pdf|excel|csv)$"),
    config: dict = Depends(get_config),
    device_repo: DeviceRepository = Depends(get_device_repository),
    dwell_repo: DwellTimeRepository = Depends(get_dwell_time_repository),
    flow_repo: FlowRepository = Depends(get_flow_repository),
    analytics_repo: AnalyticsRepository = Depends(get_analytics_repository),
    report_repo: ReportRepository = Depends(get_report_repository)
):
    """
    レポートを生成
    
    Args:
        background_tasks: バックグラウンドタスク
        report_type: レポートタイプ
        start_date: 開始日
        end_date: 終了日
        zones: 対象ゾーン
        format: 出力フォーマット
    """
    try:
        # デフォルトの日付設定
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            if report_type == "daily":
                start_date = end_date.replace(hour=0, minute=0, second=0)
            elif report_type == "weekly":
                start_date = end_date - timedelta(days=7)
            elif report_type == "monthly":
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(days=1)
        
        # レポートIDを生成
        report_id = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # バックグラウンドでレポート生成を実行
        background_tasks.add_task(
            _generate_report_task,
            report_id,
            report_type,
            start_date,
            end_date,
            zones,
            format,
            config,
            device_repo,
            dwell_repo,
            flow_repo,
            analytics_repo,
            report_repo
        )
        
        return {
            "report_id": report_id,
            "status": "generating",
            "message": "レポート生成を開始しました",
            "estimated_time": 60 if report_type == "daily" else 180  # 秒
        }
    except Exception as e:
        logger.error(f"Error initiating report generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    report_repo: ReportRepository = Depends(get_report_repository)
):
    """
    特定のレポート情報を取得
    
    Args:
        report_id: レポートID
    """
    try:
        report = await report_repo.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return {
            "report_id": report.id,
            "type": report.report_type,
            "status": report.status,
            "created_at": report.created_at,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "file_size": report.file_size,
            "download_url": f"/api/v1/reports/{report.id}/download" if report.file_path else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    report_repo: ReportRepository = Depends(get_report_repository)
):
    """
    レポートファイルをダウンロード
    
    Args:
        report_id: レポートID
    """
    try:
        report = await report_repo.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        if not report.file_path or not os.path.exists(report.file_path):
            raise HTTPException(status_code=404, detail="Report file not found")
        
        # ファイル拡張子を取得
        file_ext = Path(report.file_path).suffix
        media_type = {
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".csv": "text/csv"
        }.get(file_ext, "application/octet-stream")
        
        return FileResponse(
            path=report.file_path,
            media_type=media_type,
            filename=f"{report_id}{file_ext}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """
    レポートを削除
    
    Args:
        report_id: レポートID
    """
    # TODO: 実際の削除処理
    return {
        "message": "Report deleted successfully",
        "report_id": report_id
    }


@router.get("/templates")
async def get_report_templates():
    """
    利用可能なレポートテンプレート一覧を取得
    """
    return {
        "templates": [
            {
                "id": "daily_summary",
                "name": "日次サマリーレポート",
                "description": "1日の動線分析サマリー",
                "parameters": ["date", "zones"]
            },
            {
                "id": "weekly_analysis",
                "name": "週次分析レポート",
                "description": "1週間の詳細分析",
                "parameters": ["start_date", "end_date", "zones", "metrics"]
            },
            {
                "id": "monthly_trends",
                "name": "月次トレンドレポート",
                "description": "月間のトレンド分析",
                "parameters": ["month", "year", "comparison"]
            },
            {
                "id": "custom",
                "name": "カスタムレポート",
                "description": "カスタマイズ可能なレポート",
                "parameters": ["start_date", "end_date", "zones", "metrics", "format"]
            }
        ]
    }


async def _generate_report_task(
    report_id: str,
    report_type: str,
    start_date: datetime,
    end_date: datetime,
    zones: Optional[List[str]],
    format: str,
    config: dict,
    device_repo: DeviceRepository,
    dwell_repo: DwellTimeRepository,
    flow_repo: FlowRepository,
    analytics_repo: AnalyticsRepository,
    report_repo: ReportRepository
):
    """バックグラウンドでレポートを生成"""
    try:
        generator = ReportGenerator(config)
        
        if report_type == "daily":
            file_path = await generator.generate_daily_report(
                start_date, zones, device_repo, dwell_repo, flow_repo, report_repo
            )
        elif report_type == "weekly":
            file_path = await generator.generate_weekly_report(
                start_date, end_date, zones,
                device_repo, dwell_repo, flow_repo, analytics_repo, report_repo
            )
        else:
            # 月次レポートやカスタムレポートも同様に実装可能
            logger.warning(f"Report type {report_type} not fully implemented")
            
        logger.info(f"Report {report_id} generated successfully")
        
    except Exception as e:
        logger.error(f"Error generating report {report_id}: {e}")
        # エラー時はレポートステータスを更新
        await report_repo.update(report_id, {"status": "failed"})


@router.post("/schedule")
async def schedule_report(
    template_id: str,
    schedule: str = Query(..., regex="^(daily|weekly|monthly)$"),
    time: str = Query(..., regex="^([0-1][0-9]|2[0-3]):[0-5][0-9]$"),
    parameters: Dict = {},
    email_to: Optional[List[str]] = None
):
    """
    定期レポートをスケジュール
    
    Args:
        template_id: テンプレートID
        schedule: スケジュール（daily/weekly/monthly）
        time: 実行時刻（HH:MM形式）
        parameters: レポートパラメータ
        email_to: 送信先メールアドレス
    """
    # TODO: 実際のスケジュール登録処理
    schedule_id = f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return {
        "schedule_id": schedule_id,
        "template_id": template_id,
        "schedule": schedule,
        "time": time,
        "parameters": parameters,
        "email_to": email_to,
        "status": "active",
        "next_run": datetime.now() + timedelta(days=1)
    }