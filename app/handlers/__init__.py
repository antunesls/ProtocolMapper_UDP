from app.handlers.base import OutputHandler
from app.handlers.http_handler import HttpHandler
from app.handlers.udp_handler import UdpHandler
from app.handlers.tcp_handler import TcpHandler
from app.handlers.mqtt_handler import MqttHandler
from app.handlers.ui24r_handler import UI24RHandler
from app.handlers.sequence_handler import SequenceHandler
from app.handlers.ramp_handler import RampHandler

HANDLER_REGISTRY: dict[str, OutputHandler] = {
    "http": HttpHandler(),
    "udp": UdpHandler(),
    "tcp": TcpHandler(),
    "mqtt": MqttHandler(),
    "ui24r": UI24RHandler(),
    "sequence": SequenceHandler(),
    "ramp": RampHandler(),
}

__all__ = ["HANDLER_REGISTRY", "OutputHandler"]
