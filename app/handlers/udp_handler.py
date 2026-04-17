import asyncio
from typing import Any

from app.handlers.base import OutputHandler
from app.handlers.template import render_config


class UdpHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        cfg = render_config(config, raw_data, source_addr)
        host: str = cfg["host"]
        port: int = int(cfg["port"])
        data: str = cfg.get("data", raw_data)

        loop = asyncio.get_event_loop()

        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol,
            remote_addr=(host, port),
        )
        try:
            transport.sendto(data.encode())
        finally:
            transport.close()

        return f"UDP sent to {host}:{port}"
