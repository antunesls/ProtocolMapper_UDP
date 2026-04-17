import re
from typing import Any

from app.db.repository import list_mappings


def _normalize_hex(value: str) -> str:
    """Normalize hex representations: '0x01', '\\x01', '01' → '01'."""
    v = value.strip().lower()
    if v.startswith("0x"):
        return v[2:]
    if v.startswith("\\x"):
        return v[2:]
    return v


async def find_match(raw_data: str) -> dict[str, Any] | None:
    """Return the first enabled mapping that matches raw_data, or None."""
    rules = await list_mappings(enabled_only=True)

    for rule in rules:
        input_type: str = rule["input_type"]
        pattern: str = rule["input_pattern"]

        matched = False
        if input_type == "exact_hex":
            # Compare normalized hex representations
            matched = _normalize_hex(raw_data) == _normalize_hex(pattern)
        elif input_type == "exact_text":
            matched = raw_data.strip() == pattern.strip()
        elif input_type == "regex":
            try:
                matched = bool(re.search(pattern, raw_data))
            except re.error:
                matched = False

        if matched:
            return rule

    return None
