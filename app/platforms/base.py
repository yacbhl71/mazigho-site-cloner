from abc import ABC, abstractmethod
from typing import Any

class BaseExtractor(ABC):
    def __init__(self, base_url: str, client: Any, page: Any | None = None):
        self.base_url, self.client, self.page = base_url.rstrip('/'), client, page
    @abstractmethod
    async def extract(self) -> dict[str, Any]: ...
