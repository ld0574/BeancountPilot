"""
WebSocket routes for progress updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/classify")
async def classify_progress(websocket: WebSocket):
    """Simple progress channel for classification"""
    await websocket.accept()
    try:
        await websocket.send_json({"status": "connected"})
        while True:
            message = await websocket.receive_json()
            event = message.get("event")
            if event == "start":
                await websocket.send_json({"status": "started"})
            elif event == "progress":
                await websocket.send_json({"status": "progress", "data": message.get("data")})
            elif event == "done":
                await websocket.send_json({"status": "done"})
            else:
                await websocket.send_json({"status": "unknown", "data": message})
    except WebSocketDisconnect:
        return
