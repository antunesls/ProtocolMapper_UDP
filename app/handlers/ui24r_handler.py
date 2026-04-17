"""
Soundcraft UI24R / UI16 / UI12 WebSocket handler.

Protocol (reverse-engineered from soundcraft-ui-main):
  - URL: ws://<host>:<port>/   (port 80 = mixer built-in web server)
  - All messages use socket.io 0.9 envelope:  "3:::<payload>"
  - Keepalive:  send  "3:::ALIVE"  every 1 second while connected
  - Set value:  send  "3:::SETD^<path>^<value>"
                e.g.  "3:::SETD^i.0.mix^0.75"      (channel 1 fader to 75%)
                      "3:::SETD^i.0.mute^1"         (channel 1 mute on)
                      "3:::SETD^mgmask^<bitmask>"   (mute groups)

output_config schema:
  {
    "host":     "192.168.1.100",        # mixer IP — required
    "port":     80,                     # optional, default 80
    "commands": [                       # list of raw commands WITHOUT "3:::" prefix
      "SETD^i.0.mute^1",
      "SETD^i.0.mix^0.75"
    ],
    "delay_ms": 50                      # optional delay (ms) between commands, default 0
  }

Template variables ${raw_data} and ${source_ip} are available in command strings.
"""

import asyncio
import logging
from typing import Any

from app.handlers.base import OutputHandler
from app.handlers.template import render_config

logger = logging.getLogger(__name__)

_ENVELOPE_PREFIX = "3:::"
_KEEPALIVE_INTERVAL = 1.0  # seconds


# ---------------------------------------------------------------------------
# WebSocket connectivity (websockets >= 12 asyncio API)
# ---------------------------------------------------------------------------

try:
    from websockets.asyncio.client import connect as ws_connect

    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


class _MixerConn:
    """Persistent WebSocket connection to a single mixer with auto-keepalive."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._ws = None
        self._keepalive_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def _url(self) -> str:
        return f"ws://{self.host}:{self.port}/"

    # ------------------------------------------------------------------
    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            try:
                if self._ws is not None:
                    await self._ws.send(f"{_ENVELOPE_PREFIX}ALIVE")
            except Exception:
                break  # connection gone; _ensure_connected will handle it

    # ------------------------------------------------------------------
    async def _ensure_connected(self):
        if self._ws is not None:
            try:
                await asyncio.wait_for(self._ws.ping(), timeout=3)
                return self._ws
            except Exception:
                logger.warning("UI24R: lost connection to %s — reconnecting", self._url)
                self._ws = None
                if self._keepalive_task:
                    self._keepalive_task.cancel()
                    self._keepalive_task = None

        logger.info("UI24R: connecting to %s", self._url)
        self._ws = await ws_connect(self._url, open_timeout=10)
        loop = asyncio.get_event_loop()
        self._keepalive_task = loop.create_task(self._keepalive_loop())
        logger.info("UI24R: connected to %s", self._url)
        return self._ws

    # ------------------------------------------------------------------
    async def send(self, command: str) -> None:
        async with self._lock:
            ws = await self._ensure_connected()
            await ws.send(f"{_ENVELOPE_PREFIX}{command}")

    async def close(self) -> None:
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

class _UI24RConnectionPool:
    """Singleton pool — reuses connections keyed by (host, port)."""

    def __init__(self) -> None:
        self._pool: dict[tuple[str, int], _MixerConn] = {}

    def get(self, host: str, port: int) -> _MixerConn:
        key = (host, port)
        if key not in self._pool:
            self._pool[key] = _MixerConn(host, port)
        return self._pool[key]

    async def close_all(self) -> None:
        for conn in list(self._pool.values()):
            await conn.close()
        self._pool.clear()


# Module-level singleton imported by main.py for shutdown
connection_pool = _UI24RConnectionPool()


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class UI24RHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        if not _WS_AVAILABLE:
            raise RuntimeError(
                "websockets package not available. Run: pip install websockets>=12"
            )

        cfg = render_config(config, raw_data, source_addr)
        host: str = cfg["host"]
        port: int = int(cfg.get("port", 80))
        commands: list[str] = cfg.get("commands", [])
        delay_ms: float = float(cfg.get("delay_ms", 0))

        if not commands:
            return f"UI24R {host}:{port} — no commands specified"

        conn = connection_pool.get(host, port)
        sent: list[str] = []

        for cmd in commands:
            await conn.send(cmd)
            sent.append(cmd)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

        return f"UI24R {host}:{port} — sent {len(sent)} cmd(s): {'; '.join(sent)}"
