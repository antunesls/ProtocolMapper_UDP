from abc import ABC, abstractmethod
from typing import Any


class OutputHandler(ABC):
    @abstractmethod
    async def execute(self, config: dict[str, Any], raw_data: str, source_addr: str) -> str:
        """Execute the output action. Returns a human-readable result string."""
