"""
Ramp handler — interpolates a numeric value from `from_value` to `to_value`
over `duration_ms` milliseconds, firing an output action on every step.

Easing functions ported from soundcraft-ui-main/src/lib/utils/transitions/easings.ts:
  - linear:      t
  - ease_in:     t²
  - ease_out:    t(2 - t)
  - ease_in_out: t²(3 - 2t)

output_config schema:
  {
    "from_value": 0.0,          # start value (float)   — required
    "to_value":   0.8,          # end value (float)     — required
    "duration_ms": 5000,        # total duration in ms  — required
    "easing":     "linear",     # optional: linear | ease_in | ease_out | ease_in_out
    "fps":        25,           # optional: steps per second, default 25
    "action": {                 # the action fired on every step
      "output_type": "ui24r",
      "output_config": {
        "host": "192.168.1.100",
        "commands": ["SETD^i.0.mix^{value}"]
      }
    }
  }

The placeholder `{value}` inside any string in output_config is replaced with the
current interpolated value (rounded to 6 decimal places) at each step.
"""

import asyncio
import copy
import logging
import math
from typing import Any, Callable

from app.handlers.base import OutputHandler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Easing functions (ported from easings.ts)
# ---------------------------------------------------------------------------

EASING_FUNCTIONS: dict[str, Callable[[float], float]] = {
    "linear":      lambda t: t,
    "ease_in":     lambda t: t * t,
    "ease_out":    lambda t: t * (2.0 - t),
    "ease_in_out": lambda t: t * t * (3.0 - 2.0 * t),
}


# ---------------------------------------------------------------------------
# Template: replace {value} recursively in config dicts
# ---------------------------------------------------------------------------

def _inject_value(obj: Any, value: float) -> Any:
    """Recursively replace '{value}' placeholder in strings/dicts/lists."""
    value_str = f"{value:.6f}"
    if isinstance(obj, str):
        return obj.replace("{value}", value_str)
    if isinstance(obj, dict):
        return {k: _inject_value(v, value) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inject_value(item, value) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class RampHandler(OutputHandler):
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        # Lazy import to avoid circular dependency (registry not built yet at module load)
        from app.handlers import HANDLER_REGISTRY  # noqa: PLC0415

        from_value: float = float(config["from_value"])
        to_value:   float = float(config["to_value"])
        duration_ms: float = float(config["duration_ms"])
        fps:        float = float(config.get("fps", 25))
        easing_name: str  = config.get("easing", "linear").lower()
        action:     dict  = config["action"]

        easing_fn = EASING_FUNCTIONS.get(easing_name, EASING_FUNCTIONS["linear"])

        # Number of discrete steps (at least 1)
        step_time_ms = 1000.0 / fps
        steps = max(1, math.ceil(duration_ms / step_time_ms))

        output_type: str = action["output_type"]
        handler = HANDLER_REGISTRY.get(output_type)
        if handler is None:
            raise ValueError(f"Ramp: unknown output_type '{output_type}'")

        sent = 0
        errors: list[str] = []

        for i in range(steps):
            t = (i + 1) / steps
            eased_t = easing_fn(t)
            current_value = round(from_value + eased_t * (to_value - from_value), 6)

            step_config = _inject_value(copy.deepcopy(action["output_config"]), current_value)

            try:
                await handler.execute(step_config, raw_data, source_addr)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"step {i + 1}: {exc}")
                logger.warning("Ramp step %d error: %s", i + 1, exc)

            if i < steps - 1:
                await asyncio.sleep(step_time_ms / 1000.0)

        range_str = f"{from_value}→{to_value}"
        result = f"Ramp {range_str} {easing_name} {duration_ms}ms: {sent}/{steps} steps sent"
        if errors:
            result += f" | {len(errors)} error(s): {errors[0]}"
        return result
