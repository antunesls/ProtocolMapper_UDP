import string
from typing import Any


def _render(template: str, raw_data: str, source_addr: str) -> str:
    """Replace ${raw_data} and ${source_ip} placeholders in template strings."""
    host, _, port = source_addr.partition(":")
    mapping = {"raw_data": raw_data, "source_ip": host, "source_port": port}
    return string.Template(template.replace("${", "$")).safe_substitute(mapping)


def render_config(config: dict[str, Any], raw_data: str, source_addr: str) -> dict[str, Any]:
    """Recursively apply template substitution to all string values in config."""
    result: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, str):
            result[key] = _render(value, raw_data, source_addr)
        elif isinstance(value, dict):
            result[key] = render_config(value, raw_data, source_addr)
        else:
            result[key] = value
    return result
