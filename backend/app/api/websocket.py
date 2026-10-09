import json
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.engine.alerts.dispatcher import alert_dispatcher

router = APIRouter(tags=["WebSocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast_json(self, data: dict):
        dead_connections = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(data))
            except Exception:
                dead_connections.add(connection)
        for dc in dead_connections:
            self.disconnect(dc)

ws_manager = ConnectionManager()

# Hook into alert_dispatcher
alert_dispatcher.set_ws_broadcast_callback(ws_manager.broadcast_json)

@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open and receive optional ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
