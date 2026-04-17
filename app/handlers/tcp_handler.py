import asyncio
from typing import Any

from app.handlers.base import OutputHandler
from app.handlers.template import render_config


class TcpHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        cfg = render_config(config, raw_data, source_addr)
        host: str = cfg["host"]
        port: int = int(cfg["port"])
        data: str = cfg.get("data", raw_data)
        timeout: float = float(cfg.get("timeout", 10.0))

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        try:
            writer.write(data.encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

        return f"TCP sent to {host}:{port}"
