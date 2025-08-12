"""ヒートマップ関連のAPIルート"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from collections import defaultdict
import os
import logging
import numpy as np

from src.api.schemas.heatmap import (
    HeatmapRequest, HeatmapResponse, HeatmapData,
    RealtimeHeatmap, HistoricalHeatmap, ZoneHeatmap
)
from src.api.dependencies import (
    get_heatmap_repository,
    get_device_repository,
    get_config
)
from src.database.repositories import (
    HeatmapRepository,
    DeviceRepository
)
from src.visualization.heatmap_generator import HeatmapGenerator


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=HeatmapResponse)
async def generate_heatmap(
    request: HeatmapRequest,
    heatmap_repo: HeatmapRepository = Depends(get_heatmap_repository),
    config: dict = Depends(get_config)
):
    """
    ヒートマップを生成
    
    Args:
        request: ヒートマップ生成リクエスト
    """
    try:
        # ヒートマップ生成器を初期化
        generator = HeatmapGenerator(config)
        
        # 時間範囲の設定
        end_time = request.end_time or datetime.now()
        start_time = request.start_time or (end_time - timedelta(minutes=5))
        
        # データベースからヒートマップデータを取得
        heatmap_data = await heatmap_repo.get_heatmap_data(
            timestamp=end_time,
            time_window=int((end_time - start_time).total_seconds() / 60)
        )
        
        # グリッドサイズを計算
        layout = config.get('layout', {})
        width = layout.get('width', 100)
        height = layout.get('height', 50)
        resolution = request.resolution or 1.0
        grid_width = int(width / resolution)
        grid_height = int(height / resolution)
        
        # ヒートマップデータを2D配列に変換
        grid = np.zeros((grid_height, grid_width))
        for data in heatmap_data:
            if data.x < grid_width and data.y < grid_height:
                grid[data.y, data.x] = data.density
        
        # 統計情報を計算
        statistics = {
            "max_density": float(np.max(grid)),
            "min_density": float(np.min(grid)),
            "avg_density": float(np.mean(grid)),
            "total_points": len(heatmap_data),
            "coverage": float(np.count_nonzero(grid) / grid.size)
        }
        
        return HeatmapResponse(
            data=HeatmapData(
                grid_size=(grid_width, grid_height),
                resolution=resolution,
                data=grid.tolist(),
                max_value=statistics["max_density"],
                min_value=statistics["min_density"],
                timestamp=end_time
            ),
            image_url=None,  # 画像生成は別途実装
            statistics=statistics
        )
    except Exception as e:
        logger.error(f"Error generating heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime", response_model=RealtimeHeatmap)
async def get_realtime_heatmap(
    device_repo: DeviceRepository = Depends(get_device_repository),
    heatmap_repo: HeatmapRepository = Depends(get_heatmap_repository)
):
    """
    リアルタイムヒートマップを取得
    """
    try:
        # アクティブデバイスを取得
        active_devices = await device_repo.get_active_devices(minutes=5)
        
        # ゾーン別に集計
        zone_data = {}
        for device in active_devices:
            if device.current_zone:
                if device.current_zone not in zone_data:
                    zone_data[device.current_zone] = {
                        "zone_id": device.current_zone,
                        "density": 0,
                        "device_count": 0,
                        "average_signal_strength": 0
                    }
                zone_data[device.current_zone]["device_count"] += 1
        
        # 密度を計算（デバイス数/ゾーン面積で正規化）
        zones = []
        for zone_id, data in zone_data.items():
            # ゾーン面積で正規化（仮に各ゾーン100平米として計算）
            data["density"] = data["device_count"] / 100.0
            zones.append(data)
        
        return RealtimeHeatmap(
            zones=zones,
            total_devices=len(active_devices),
            timestamp=datetime.now(),
            update_interval=5
        )
    except Exception as e:
        logger.error(f"Error getting realtime heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historical", response_model=HistoricalHeatmap)
async def get_historical_heatmap(
    period: str = Query("hourly", regex="^(hourly|daily|weekly|monthly)$"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    aggregation: str = Query("average", regex="^(average|max|sum)$"),
    heatmap_repo: HeatmapRepository = Depends(get_heatmap_repository)
):
    """
    履歴ヒートマップを取得
    
    Args:
        period: 期間タイプ
        start_time: 開始時刻
        end_time: 終了時刻
        aggregation: 集計方法
    """
    try:
        # デフォルトの時間範囲設定
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            if period == "hourly":
                start_time = end_time - timedelta(hours=24)
            elif period == "daily":
                start_time = end_time - timedelta(days=7)
            elif period == "weekly":
                start_time = end_time - timedelta(weeks=4)
            else:  # monthly
                start_time = end_time - timedelta(days=365)
        
        # 期間に応じたインターバルを設定
        intervals = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "monthly": timedelta(days=30)
        }
        interval = intervals[period]
        
        # データポイントを生成
        data_points = []
        current_time = start_time
        while current_time <= end_time:
            # 各時点のヒートマップデータを取得
            heatmap_data = await heatmap_repo.get_heatmap_data(
                timestamp=current_time,
                time_window=60  # 1時間のウィンドウ
            )
            
            # 集計値を計算
            if heatmap_data:
                densities = [d.density for d in heatmap_data]
                if aggregation == "average":
                    value = sum(densities) / len(densities)
                elif aggregation == "max":
                    value = max(densities)
                else:  # sum
                    value = sum(densities)
            else:
                value = 0
            
            data_points.append({
                "timestamp": current_time,
                "value": value,
                "device_count": len(heatmap_data)
            })
            
            current_time += interval
        
        return HistoricalHeatmap(
            period=period,
            data_points=data_points,
            aggregation_method=aggregation,
            comparison=None
        )
    except Exception as e:
        logger.error(f"Error getting historical heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_current_heatmap(
    device_repo: DeviceRepository = Depends(get_device_repository),
    config: dict = Depends(get_config)
):
    """
    現在のデバイス位置からヒートマップデータを生成
    """
    try:
        # アクティブなデバイスを取得
        active_devices = await device_repo.get_active_devices(minutes=5)
        
        # 施設のサイズを取得
        layout = config.get('facility', {}).get('dimensions', {})
        width = layout.get('width', 100)
        height = layout.get('height', 50)
        
        # グリッドサイズ（5メートル単位）
        grid_size = 5
        grid_width = int(width / grid_size)
        grid_height = int(height / grid_size)
        
        # グリッドごとのデバイス数をカウント
        grid_data = []
        for device in active_devices:
            if device.current_x is not None and device.current_y is not None:
                grid_x = int(device.current_x / grid_size)
                grid_y = int(device.current_y / grid_size)
                
                # グリッドデータに追加
                grid_data.append({
                    'x': grid_x,
                    'y': grid_y,
                    'density': 1.0  # 各デバイスは1としてカウント
                })
        
        # 同じグリッドのデバイスをまとめる
        from collections import defaultdict
        grid_counts = defaultdict(int)
        for item in grid_data:
            key = (item['x'], item['y'])
            grid_counts[key] += 1
        
        # 結果を整形
        result_data = []
        max_count = max(grid_counts.values()) if grid_counts else 1
        for (x, y), count in grid_counts.items():
            result_data.append({
                'x': x,
                'y': y,
                'density': count / max_count  # 正規化
            })
        
        return {
            'data': result_data,
            'grid_size': grid_size,
            'width': grid_width,
            'height': grid_height,
            'device_count': len(active_devices),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting current heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/zones", response_model=List[ZoneHeatmap])
async def get_zone_heatmaps(
    heatmap_repo: HeatmapRepository = Depends(get_heatmap_repository),
    config: dict = Depends(get_config)
):
    """
    ゾーン別ヒートマップを取得
    """
    try:
        # 設定からゾーン情報を取得
        zones_config = config.get('layout', {}).get('zones', [])
        
        # 各ゾーンの最新密度を取得
        zone_heatmaps = []
        for zone in zones_config:
            zone_id = zone.get('id')
            if zone_id:
                density = await heatmap_repo.get_zone_density(
                    zone_id=zone_id,
                    timestamp=datetime.now()
                )
                
                zone_heatmaps.append(ZoneHeatmap(
                    zone_id=zone_id,
                    zone_name=zone.get('name', zone_id),
                    current_density=density,
                    max_capacity=zone.get('max_capacity', 100),
                    occupancy_rate=min(density * 100, 100),  # パーセンテージ
                    color_code=_get_color_code(density),
                    timestamp=datetime.now()
                ))
        
        return zone_heatmaps
    except Exception as e:
        logger.error(f"Error getting zone heatmaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _get_color_code(density: float) -> str:
    """密度に基づいてカラーコードを返す"""
    if density < 0.2:
        return "#00FF00"  # 緑
    elif density < 0.5:
        return "#FFFF00"  # 黄
    elif density < 0.8:
        return "#FFA500"  # オレンジ
    else:
        return "#FF0000"  # 赤


@router.get("/export/{filename}")
async def export_heatmap(
    filename: str,
    format: str = Query("png", regex="^(png|jpg|svg|pdf)$")
):
    """
    ヒートマップ画像をエクスポート
    
    Args:
        filename: ファイル名
        format: 出力フォーマット
    """
    # TODO: 実際のエクスポート処理
    export_path = f"exports/heatmaps/{filename}.{format}"
    
    if not os.path.exists(export_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=export_path,
        media_type=f"image/{format}",
        filename=f"{filename}.{format}"
    )


@router.get("/compare")
async def compare_heatmaps(
    period1_start: datetime = Query(..., description="期間1開始"),
    period1_end: datetime = Query(..., description="期間1終了"),
    period2_start: datetime = Query(..., description="期間2開始"),
    period2_end: datetime = Query(..., description="期間2終了")
):
    """
    2つの期間のヒートマップを比較
    
    Args:
        period1_start: 期間1の開始時刻
        period1_end: 期間1の終了時刻
        period2_start: 期間2の開始時刻
        period2_end: 期間2の終了時刻
    """
    # TODO: 実際の比較処理
    return {
        "period1": {
            "start": period1_start,
            "end": period1_end,
            "average_density": 0.0,
            "peak_density": 0.0
        },
        "period2": {
            "start": period2_start,
            "end": period2_end,
            "average_density": 0.0,
            "peak_density": 0.0
        },
        "difference": {
            "average_change": 0.0,
            "peak_change": 0.0,
            "significant_zones": []
        }
    }


@router.get("/timelapse")
async def get_heatmap_timelapse(
    start_time: datetime = Query(..., description="開始時刻"),
    end_time: datetime = Query(..., description="終了時刻"),
    interval: int = Query(60, ge=1, description="間隔（分）")
):
    """
    タイムラプスヒートマップデータを取得
    
    Args:
        start_time: 開始時刻
        end_time: 終了時刻
        interval: フレーム間隔（分）
    """
    # TODO: 実際のタイムラプスデータ生成
    return {
        "frames": [],
        "total_frames": 0,
        "interval_minutes": interval,
        "start_time": start_time,
        "end_time": end_time
    }