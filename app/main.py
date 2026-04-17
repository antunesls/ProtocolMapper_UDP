import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import router as api_router
from app.config import get_settings
from app.core.log_buffer import log_buffer
from app.core.udp_server import udp_server
from app.db.database import init_db
from app.db.repository import get_settings_record

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Jinja2 templates
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


# ---------------------------------------------------------------------------
# Basic Auth middleware
# ---------------------------------------------------------------------------
_OPEN_PATHS = {"/docs", "/openapi.json", "/redoc"}


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # WebSocket auth is handled inside the WS endpoint itself
        if request.url.path.startswith("/ws/"):
            return await call_next(request)

        # Skip if no password is configured (dev mode)
        if not settings.admin_password_hash:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                username, _, password = decoded.partition(":")
                import bcrypt as _bcrypt
                if (
                    secrets.compare_digest(username, settings.admin_username)
                    and _bcrypt.checkpw(password.encode(), settings.admin_password_hash.encode())
                ):
                    return await call_next(request)
            except Exception:  # noqa: BLE001
                pass

        return Response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="ProtocolMapper"'},
            content="Unauthorized",
        )


# ---------------------------------------------------------------------------
# Lifespan: init DB and start UDP server
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    await init_db()
    db_settings = await get_settings_record()
    log_buffer.resize(db_settings["log_max_entries"])

    await udp_server.start(db_settings["listen_ip"], db_settings["listen_port"])
    logger.info("ProtocolMapper started. Web UI → http://%s:%d", settings.host, settings.port)

    yield

    await udp_server.stop()

    from app.handlers.ui24r_handler import connection_pool as ui24r_pool
    await ui24r_pool.close_all()

    logger.info("ProtocolMapper stopped.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ProtocolMapper UDP",
    description="UDP Command Gateway — maps incoming UDP packets to HTTP/UDP/TCP/MQTT actions.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(BasicAuthMiddleware)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Web page routes
# ---------------------------------------------------------------------------
def _ws_url(request: Request) -> str:
    """Build the WebSocket URL, injecting basic-auth token into query param."""
    scheme = "wss" if request.url.scheme == "https" else "ws"
    base = f"{scheme}://{request.url.netloc}/ws/logs"

    # If no password configured, no token needed
    if not settings.admin_password_hash:
        return base

    # Read credentials from the Authorization header and forward as token
    auth = request.headers.get("Authorization", "")
    token = auth[6:] if auth.startswith("Basic ") else ""
    return f"{base}?token={token}"


@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"ws_url": _ws_url(request)})


@app.get("/mappings", response_class=HTMLResponse)
async def page_mappings(request: Request):
    return templates.TemplateResponse(request, "mappings.html")


@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    return templates.TemplateResponse(request, "settings.html")
