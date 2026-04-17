import asyncio
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


@dataclass
class LogEntry:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    direction: str = "IN"          # "IN" | "OUT"
    source_addr: str = ""
    raw_data: str = ""
    matched_rule: str | None = None
    output_result: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LogBuffer:
    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: deque[LogEntry] = deque(maxlen=maxlen)
        self._subscribers: list[WebSocket] = []
        self._lock = asyncio.Lock()

    def resize(self, maxlen: int) -> None:
        new_buf: deque[LogEntry] = deque(maxlen=maxlen)
        new_buf.extend(self._buf)
        self._buf = new_buf

    def recent(self, n: int | None = None) -> list[dict[str, Any]]:
        entries = list(self._buf)
        if n is not None:
            entries = entries[-n:]
        return [e.to_dict() for e in entries]

    async def append(self, entry: LogEntry) -> None:
        self._buf.append(entry)
        await self._broadcast(entry.to_dict())

    async def subscribe(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subscribers.append(ws)

    async def unsubscribe(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not ws]

    async def _broadcast(self, data: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._subscribers):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.unsubscribe(ws)


# Global singleton — imported by all modules
log_buffer = LogBuffer()
