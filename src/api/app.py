"""FastAPI WebAPIアプリケーション"""
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
from datetime import datetime

# 内部モジュール
from src.core.config_loader import load_config
from src.database.connection import DatabaseConnection
from src.api.routes import devices, analytics, heatmap, reports, trajectories, dwell_time, flow, realtime
from src.api.websocket import ConnectionManager


# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    # 起動時の処理
    logger.info("Starting FastAPI application...")
    
    # 設定読み込み
    config = load_config()
    app.state.config = config
    
    # データベース接続
    db_conn = DatabaseConnection(config['database'])
    await db_conn.connect()
    app.state.db = db_conn
    
    # WebSocket接続マネージャー
    app.state.ws_manager = ConnectionManager()
    
    logger.info("FastAPI application started successfully")
    
    yield
    
    # 終了時の処理
    logger.info("Shutting down FastAPI application...")
    await db_conn.disconnect()
    logger.info("FastAPI application shut down")


# FastAPIアプリケーション初期化
app = FastAPI(
    title="Bluetooth動線分析システムAPI",
    description="Bluetooth信号を使用した人流分析・可視化システムのREST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では制限すること
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ルーターの登録
app.include_router(devices.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(heatmap.router, prefix="/api/v1/heatmap", tags=["heatmap"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(trajectories.router, prefix="/api/v1/trajectories", tags=["trajectories"])
app.include_router(dwell_time.router, prefix="/api/v1/dwell-time", tags=["dwell_time"])
app.include_router(flow.router, prefix="/api/v1/flow", tags=["flow"])
app.include_router(realtime.router, prefix="/api/v1/realtime", tags=["realtime"])


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "application": "Bluetooth Motion Analysis System",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    try:
        # データベース接続確認
        db_status = "connected" if app.state.db and app.state.db.pool else "disconnected"
        
        return {
            "status": "healthy",
            "database": db_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocketエンドポイント"""
    await app.state.ws_manager.connect(websocket)
    try:
        while True:
            # クライアントからのメッセージを受信
            data = await websocket.receive_text()
            
            # メッセージを処理（例：リアルタイムデータの購読）
            if data == "subscribe:realtime":
                # リアルタイムデータの送信を開始
                asyncio.create_task(send_realtime_data(websocket))
            
    except WebSocketDisconnect:
        app.state.ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")


async def send_realtime_data(websocket: WebSocket):
    """リアルタイムデータを送信"""
    try:
        while True:
            # ここでリアルタイムデータを取得
            data = {
                "type": "realtime_update",
                "timestamp": datetime.now().isoformat(),
                "active_devices": 0,  # 実際のデータに置き換え
                "zones": {}  # 実際のデータに置き換え
            }
            
            await app.state.ws_manager.send_personal_message(data, websocket)
            await asyncio.sleep(5)  # 5秒ごとに更新
            
    except Exception as e:
        logger.error(f"Error sending realtime data: {e}")


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """404エラーハンドラー"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "path": str(request.url)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """500エラーハンドラー"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )