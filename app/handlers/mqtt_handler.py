from typing import Any

from app.handlers.base import OutputHandler
from app.handlers.template import render_config

try:
    import aiomqtt  # optional dependency

    class MqttHandler(OutputHandler):
        async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
            cfg = render_config(config, raw_data, source_addr)
            broker: str = cfg["broker"]
            port: int = int(cfg.get("port", 1883))
            topic: str = cfg["topic"]
            payload: str = cfg.get("payload", raw_data)
            qos: int = int(cfg.get("qos", 0))

            async with aiomqtt.Client(broker, port=port) as client:
                await client.publish(topic, payload=payload.encode(), qos=qos)

            return f"MQTT published to {broker}:{port} topic={topic}"

except ImportError:  # pragma: no cover
    class MqttHandler(OutputHandler):  # type: ignore[no-redef]
        async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
            raise RuntimeError(
                "aiomqtt is not installed. Run: pip install aiomqtt"
            )
