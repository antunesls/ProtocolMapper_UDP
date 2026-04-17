"""
Sequence handler — executes multiple output actions from a single UDP trigger.

output_config schema:
  {
    "parallel": false,       # if true, run all actions concurrently with asyncio.gather()
    "actions": [
      {
        "delay_before_ms": 0,        # optional: wait before this action (ms), default 0
        "output_type": "ui24r",
        "output_config": { ... }
      },
      {
        "delay_before_ms": 1000,     # wait 1 second before this action
        "output_type": "http",
        "output_config": { "url": "http://api.local/event", "method": "POST" }
      },
      {
        "delay_before_ms": 0,
        "output_type": "ramp",
        "output_config": { ... }     # ramps can be nested inside sequences
      }
    ]
  }
"""

import asyncio
import logging
from typing import Any

from app.handlers.base import OutputHandler

logger = logging.getLogger(__name__)


class SequenceHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        # Lazy import to avoid circular dependency
        from app.handlers import HANDLER_REGISTRY  # noqa: PLC0415

        actions: list[dict[str, Any]] = config.get("actions", [])
        parallel: bool = bool(config.get("parallel", False))

        if not actions:
            return "Sequence: no actions defined"

        if parallel:
            # Run all actions concurrently (each with its own delay)
            tasks = [
                self._run_action(idx, action, raw_data, source_addr, HANDLER_REGISTRY)
                for idx, action in enumerate(actions)
            ]
            results: list[str] = await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # Run sequentially
            results = []
            for idx, action in enumerate(actions):
                result = await self._run_action(
                    idx, action, raw_data, source_addr, HANDLER_REGISTRY
                )
                results.append(result)

        ok = sum(1 for r in results if not r.startswith("ERROR"))
        total = len(results)
        summary = f"Sequence: {ok}/{total} OK"
        for i, r in enumerate(results):
            summary += f" | [{i + 1}] {r}"
        return summary

    # ------------------------------------------------------------------
    @staticmethod
    async def _run_action(
        idx: int,
        action: dict[str, Any],
        raw_data: str,
        source_addr: str,
        registry: dict,
    ) -> str:
        delay_before_ms = float(action.get("delay_before_ms", 0))
        output_type: str = action.get("output_type", "")
        output_config: dict[str, Any] = action.get("output_config", {})

        if delay_before_ms > 0:
            await asyncio.sleep(delay_before_ms / 1000.0)

        handler = registry.get(output_type)
        if handler is None:
            return f"ERROR: unknown output_type '{output_type}' in action {idx + 1}"

        try:
            result = await handler.execute(output_config, raw_data, source_addr)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sequence action %d (%s) error: %s", idx + 1, output_type, exc)
            return f"ERROR: {exc}"
