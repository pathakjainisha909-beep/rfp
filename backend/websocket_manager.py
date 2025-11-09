from fastapi import WebSocket
from typing import List
import json
from datetime import datetime


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WebSocket] Client connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WebSocket] Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"[WebSocket] Error sending personal message: {e}")
            self.disconnect(websocket)
            
    async def send_completion(self):
        """Send completion event with results"""
        message = {
            "type": "completion",
            "timestamp": datetime.now().isoformat()
        }
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass
    
    async def broadcast(self, message: str):
        """Broadcast message to all connected clients"""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"[WebSocket] Error broadcasting: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_log(self, level: str, message: str, data: dict = None):
        log_message = {
            "type": "log",
            "level": level,
            "message": message,  # message is already cleaned by pipeline
            "timestamp": self._get_timestamp()
        }
        await self.broadcast(json.dumps(log_message))


    
    async def send_progress(self, stage: str, current: int, total: int, message: str = ""):
        """Send progress update"""
        progress_message = {
            "type": "progress",
            "stage": stage,
            "current": current,
            "total": total,
            "percentage": int((current / total * 100)) if total > 0 else 0,
            "message": message,
            "timestamp": self._get_timestamp()
        }
        await self.broadcast(json.dumps(progress_message))
    
    async def send_screenshot(self, image_base64: str, caption: str = ""):
        """Screenshot disabled"""
        return
    
    async def send_pdf_status(self, pdf_name: str, status: str, reason: str = "", details: dict = None):
        """Send PDF processing status"""
        pdf_message = {
            "type": "pdf_status",
            "pdf_name": pdf_name,
            "status": status,
            "reason": reason,
            "details": details or {},
            "timestamp": self._get_timestamp()
        }
        await self.broadcast(json.dumps(pdf_message))
    
    def _get_timestamp(self):
        """Get current timestamp"""
        return datetime.now().isoformat()
