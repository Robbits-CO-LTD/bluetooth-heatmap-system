"""デバイス関連のAPIルート"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from src.api.schemas.device import (
    Device, DeviceWithPosition, DeviceTrajectory, 
    ActiveDevicesSummary, DeviceCreate, DeviceUpdate
)
from src.api.dependencies import (
    get_device_repository,
    get_trajectory_repository,
    get_dwell_time_repository
)
from src.database.repositories import (
    DeviceRepository,
    TrajectoryRepository,
    DwellTimeRepository
)


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[Device])
async def get_devices(
    skip: int = Query(0, ge=0, description="スキップ数"),
    limit: int = Query(500, ge=1, le=10000, description="取得数"),
    active_only: bool = Query(True, description="アクティブのみ"),  # デフォルトTrueに変更
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    デバイス一覧を取得
    """
    try:
        if active_only:
            # リアルタイム性を高めるたち30秒以内のデバイスのみ
            devices = await device_repo.get_active_devices(seconds=30)
            # device_idで重複を除去
            unique_devices = {}
            for device in devices:
                if device.device_id not in unique_devices:
                    unique_devices[device.device_id] = device
            devices = list(unique_devices.values())
            devices = devices[skip:skip+limit]
        else:
            # 全デバイスを取得（ページネーション付き）
            devices = await device_repo.get_all(skip=skip, limit=limit)
            # device_idで重複を除去
            unique_devices = {}
            for device in devices:
                if device.device_id not in unique_devices:
                    unique_devices[device.device_id] = device
            devices = list(unique_devices.values())
        
        # デバイスデータを整形（位置情報を含める）
        result = []
        for device in devices:
            device_dict = {
                "id": device.device_id,
                "device_id": device.device_id,
                "mac_address": device.mac_address,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "manufacturer": getattr(device, 'manufacturer', None),
                "first_seen": device.first_seen,
                "last_seen": device.last_seen,
                "total_duration": getattr(device, 'total_duration', 0.0),
                "is_active": getattr(device, 'is_active', True),
                "total_detections": device.total_detections,
                "current_x": device.current_x,
                "current_y": device.current_y,
                "current_zone": device.current_zone,
                "signal_strength": device.signal_strength
            }
            result.append(device_dict)
        
        return result
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active", response_model=ActiveDevicesSummary)
async def get_active_devices(
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    アクティブなデバイスのサマリーを取得
    """
    try:
        # リアルタイム性を高めるたち30秒以内のデバイスのみ
        active_devices = await device_repo.get_active_devices(seconds=30)
        
        # ゾーン分布を集計
        zone_distribution = {}
        device_types = {}
        
        for device in active_devices:
            # ゾーン分布
            if device.current_zone:
                zone_distribution[device.current_zone] = zone_distribution.get(device.current_zone, 0) + 1
            
            # デバイスタイプ分布
            device_type = device.device_type or "unknown"
            device_types[device_type] = device_types.get(device_type, 0) + 1
        
        return ActiveDevicesSummary(
            total_active=len(active_devices),
            zone_distribution=zone_distribution,
            device_types=device_types,
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"Error getting active devices summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}", response_model=DeviceWithPosition)
async def get_device(
    device_id: str,
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    特定のデバイス情報を取得
    
    Args:
        device_id: デバイスID
    """
    try:
        device = await device_repo.get_by_id(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # デバイスに位置情報を追加
        return DeviceWithPosition(
            device_id=device.device_id,
            mac_address=device.mac_address,
            device_type=device.device_type,
            first_seen=device.first_seen,
            last_seen=device.last_seen,
            current_position={
                "x": device.current_x or 0,
                "y": device.current_y or 0,
                "zone": device.current_zone
            } if device.current_x is not None else None,
            signal_strength=device.signal_strength,
            total_detections=device.total_detections
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/trajectory", response_model=DeviceTrajectory)
async def get_device_trajectory(
    device_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    trajectory_repo: TrajectoryRepository = Depends(get_trajectory_repository)
):
    """
    デバイスの軌跡を取得
    
    Args:
        device_id: デバイスID
        start_time: 開始時刻
        end_time: 終了時刻
    """
    try:
        # デフォルトの時間範囲（過去1時間）
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        
        trajectories = await trajectory_repo.get_device_trajectories(
            device_id, start_time, end_time
        )
        
        if not trajectories:
            # 軌跡がない場合は空の結果を返す
            return DeviceTrajectory(
                device_id=device_id,
                trajectory_id="no_trajectory",
                start_time=start_time,
                end_time=end_time,
                points=[],
                total_distance=0.0,
                average_speed=0.0
            )
        
        # 最新の軌跡を返す
        latest_trajectory = trajectories[-1]
        
        # 軌跡ポイントを整形
        points = [
            {
                "timestamp": point.timestamp,
                "x": point.x,
                "y": point.y,
                "zone": point.zone_id
            }
            for point in latest_trajectory.points
        ]
        
        return DeviceTrajectory(
            device_id=device_id,
            trajectory_id=str(latest_trajectory.id),
            start_time=latest_trajectory.start_time,
            end_time=latest_trajectory.end_time or end_time,
            points=points,
            total_distance=latest_trajectory.total_distance or 0.0,
            average_speed=latest_trajectory.average_speed or 0.0
        )
    except Exception as e:
        logger.error(f"Error getting trajectory for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Device, status_code=201)
async def create_device(
    device: DeviceCreate,
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    新しいデバイスを登録
    
    Args:
        device: デバイス作成情報
    """
    try:
        # 既存デバイスの確認
        existing = await device_repo.get_by_mac(device.mac_address)
        if existing:
            raise HTTPException(status_code=409, detail="Device already exists")
        
        # 新規デバイスを作成
        device_data = {
            "device_id": device.device_id or device.mac_address,
            "mac_address": device.mac_address,
            "device_type": device.device_type,
            "first_seen": datetime.now(),
            "last_seen": datetime.now(),
            "total_detections": 0
        }
        
        new_device = await device_repo.create(device_data)
        
        return Device(
            device_id=new_device.device_id,
            mac_address=new_device.mac_address,
            device_type=new_device.device_type,
            first_seen=new_device.first_seen,
            last_seen=new_device.last_seen,
            total_detections=new_device.total_detections
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{device_id}", response_model=Device)
async def update_device(
    device_id: str,
    device: DeviceUpdate,
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    デバイス情報を更新
    
    Args:
        device_id: デバイスID
        device: 更新情報
    """
    try:
        # 既存デバイスを取得
        existing = await device_repo.get_by_id(device_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # 更新データを準備
        update_data = {}
        if device.device_type is not None:
            update_data['device_type'] = device.device_type
        if device.current_zone is not None:
            update_data['current_zone'] = device.current_zone
        if device.current_x is not None:
            update_data['current_x'] = device.current_x
        if device.current_y is not None:
            update_data['current_y'] = device.current_y
            
        # デバイスを更新
        if update_data:
            await device_repo.update(device_id, update_data)
        
        # 更新後のデバイスを取得
        updated_device = await device_repo.get_by_id(device_id)
        
        return Device(
            device_id=updated_device.device_id,
            mac_address=updated_device.mac_address,
            device_type=updated_device.device_type,
            first_seen=updated_device.first_seen,
            last_seen=updated_device.last_seen,
            total_detections=updated_device.total_detections
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    device_repo: DeviceRepository = Depends(get_device_repository)
):
    """
    デバイスを削除
    
    Args:
        device_id: デバイスID
    """
    try:
        # デバイスの存在確認
        existing = await device_repo.get_by_id(device_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # デバイスを削除
        await device_repo.delete(device_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/dwell-times", response_model=List[Dict])
async def get_device_dwell_times(
    device_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    dwell_repo: DwellTimeRepository = Depends(get_dwell_time_repository)
):
    """
    デバイスの滞留時間履歴を取得
    
    Args:
        device_id: デバイスID
        start_time: 開始時刻
        end_time: 終了時刻
    """
    try:
        # デフォルトの時間範囲（過去24時間）
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=24)
        
        # デバイスの滞留履歴を取得
        dwell_times = await dwell_repo.get_device_dwells(
            device_id, start_time, end_time
        )
        
        # 結果を整形
        result = [
            {
                "zone_id": dwell.zone_id,
                "entry_time": dwell.entry_time,
                "exit_time": dwell.exit_time,
                "duration_seconds": dwell.duration_seconds,
                "is_active": dwell.is_active
            }
            for dwell in dwell_times
        ]
        
        return result
    except Exception as e:
        logger.error(f"Error getting dwell times for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))