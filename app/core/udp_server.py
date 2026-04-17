import asyncio
import logging

from app.core.dispatcher import dispatch

logger = logging.getLogger(__name__)


class UdpServerProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport
        addr = transport.get_extra_info("sockname")
        logger.info("UDP listener started on %s:%s", *addr)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        source_addr = f"{addr[0]}:{addr[1]}"
        try:
            raw_data = data.decode("utf-8", errors="replace").strip()
        except Exception:
            raw_data = data.hex()

        loop = asyncio.get_event_loop()
        loop.create_task(dispatch(raw_data, source_addr))

    def error_received(self, exc: Exception) -> None:
        logger.error("UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("UDP listener stopped. exc=%s", exc)


class UdpServer:
    def __init__(self) -> None:
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: UdpServerProtocol | None = None

    @property
    def is_running(self) -> bool:
        return self._transport is not None and not self._transport.is_closing()

    async def start(self, host: str, port: int) -> None:
        if self.is_running:
            await self.stop()

        loop = asyncio.get_event_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            UdpServerProtocol,
            local_addr=(host, port),
        )
        logger.info("UDP server bound to %s:%d", host, port)

    async def stop(self) -> None:
        if self._transport and not self._transport.is_closing():
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("UDP server stopped")

    async def restart(self, host: str, port: int) -> None:
        await self.stop()
        await self.start(host, port)


# Global singleton
udp_server = UdpServer()
