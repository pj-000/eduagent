"""Base model provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ProviderResponse(BaseModel):
    content: str
    raw: dict[str, Any] | None = None
    usage: dict[str, int] | None = None


class ModelProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        ...
