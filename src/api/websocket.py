"""WebSocket接続管理モジュール"""
import logging
import json
from typing import List, Dict, Any
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket接続マネージャー"""
    
    def __init__(self):
        """初期化"""
        self.active_connections: List[WebSocket] = []
        self.logger = logging.getLogger(__name__)
        
    async def connect(self, websocket: WebSocket):
        """
        新しいWebSocket接続を受け入れる
        
        Args:
            websocket: WebSocketインスタンス
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        self.logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """
        WebSocket接続を切断
        
        Args:
            websocket: WebSocketインスタンス
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")
            
    async def send_personal_message(self, message: Any, websocket: WebSocket):
        """
        特定のクライアントにメッセージを送信
        
        Args:
            message: 送信するメッセージ
            websocket: 対象のWebSocket
        """
        try:
            if isinstance(message, dict):
                message = json.dumps(message, ensure_ascii=False)
            await websocket.send_text(message)
        except Exception as e:
            self.logger.error(f"Error sending message to client: {e}")
            
    async def broadcast(self, message: Any):
        """
        全てのクライアントにメッセージをブロードキャスト
        
        Args:
            message: ブロードキャストするメッセージ
        """
        if isinstance(message, dict):
            message = json.dumps(message, ensure_ascii=False)
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                self.logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
                
        # 切断されたクライアントを削除
        for conn in disconnected:
            self.disconnect(conn)
            
    async def broadcast_to_group(self, message: Any, group: str):
        """
        特定のグループにメッセージをブロードキャスト
        
        Args:
            message: ブロードキャストするメッセージ
            group: グループ名
        """
        # グループ管理機能は必要に応じて実装
        pass
        
    def get_connection_count(self) -> int:
        """
        アクティブな接続数を取得
        
        Returns:
            接続数
        """
        return len(self.active_connections)