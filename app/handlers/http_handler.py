import json
from typing import Any

import httpx

from app.handlers.base import OutputHandler
from app.handlers.template import render_config


class HttpHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        cfg = render_config(config, raw_data, source_addr)
        url: str = cfg["url"]
        method: str = cfg.get("method", "POST").upper()
        headers: dict[str, str] = cfg.get("headers", {})
        body: Any = cfg.get("body", None)
        timeout: float = float(cfg.get("timeout", 10.0))

        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                pass  # send as raw string content

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=body if isinstance(body, (dict, list)) else None,
                content=body.encode() if isinstance(body, str) else None,
            )
        return f"HTTP {response.status_code} {response.reason_phrase}"
