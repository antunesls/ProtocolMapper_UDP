import time
from typing import Any

from app.core.log_buffer import LogEntry, log_buffer
from app.core.mapper import find_match
from app.handlers import HANDLER_REGISTRY


async def dispatch(raw_data: str, source_addr: str) -> None:
    """Process an incoming UDP payload: match → execute handler → log."""
    start = time.perf_counter()

    # Log the incoming packet immediately
    in_entry = LogEntry(
        direction="IN",
        source_addr=source_addr,
        raw_data=raw_data,
    )

    rule: dict[str, Any] | None = await find_match(raw_data)

    if rule is None:
        in_entry.matched_rule = None
        in_entry.output_result = "No matching rule"
        in_entry.latency_ms = round((time.perf_counter() - start) * 1000, 2)
        await log_buffer.append(in_entry)
        return

    in_entry.matched_rule = rule["name"]

    handler = HANDLER_REGISTRY.get(rule["output_type"])
    if handler is None:
        in_entry.output_result = f"Unknown output type: {rule['output_type']}"
        in_entry.latency_ms = round((time.perf_counter() - start) * 1000, 2)
        await log_buffer.append(in_entry)
        return

    try:
        result = await handler.execute(rule["output_config"], raw_data, source_addr)
    except Exception as exc:  # noqa: BLE001
        result = f"ERROR: {exc}"

    latency = round((time.perf_counter() - start) * 1000, 2)
    in_entry.output_result = result
    in_entry.latency_ms = latency
    await log_buffer.append(in_entry)

    # Also log the outgoing action
    out_entry = LogEntry(
        direction="OUT",
        source_addr=source_addr,
        raw_data=f"{rule['output_type'].upper()} → {result}",
        matched_rule=rule["name"],
        output_result=result,
        latency_ms=latency,
    )
    await log_buffer.append(out_entry)
