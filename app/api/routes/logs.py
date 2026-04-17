import base64
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.core.log_buffer import log_buffer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["logs"])
_settings = get_settings()


def _verify_ws_token(token: str) -> bool:
    """Validate base64(username:password) token for WebSocket connections."""
    try:
        decoded = base64.b64decode(token).decode()
        username, _, password = decoded.partition(":")
        import bcrypt as _bcrypt
        return (
            username == _settings.admin_username
            and _bcrypt.checkpw(password.encode(), _settings.admin_password_hash.encode())
        )
    except Exception:  # noqa: BLE001
        return False


@router.get("/api/logs")
async def get_logs(n: int = Query(default=100, ge=1, le=10000)):
    return log_buffer.recent(n)


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket, token: str = Query(default="")):
    if _settings.admin_password_hash and not _verify_ws_token(token):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await log_buffer.subscribe(websocket)
    try:
        while True:
            # Keep connection alive; client drives pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await log_buffer.unsubscribe(websocket)
