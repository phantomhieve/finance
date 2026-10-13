"""Abstract base adapter for AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from ..types import AINode

T = TypeVar("T", bound=BaseModel)


class BaseAIAdapter(ABC):
    """Abstract interface that every provider adapter must implement."""

    @abstractmethod
    def generate_text(
        self,
        node: AINode,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate unstructured text from the model."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        node: AINode,
        schema: type[T],
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> T:
        """Generate a validated Pydantic model instance from the model."""
        pass

    def fetch_macro_grounding(
        self,
        node: AINode,
        prompt: str,
        **kwargs: Any,
    ) -> dict | None:
        """Fetch live macroeconomic context using search grounding (if supported by provider)."""
        return None

    def is_configured(self, node: AINode) -> bool:
        """Check if required configuration/credentials exist for this node."""
        return bool(node.api_keys) or bool(node.base_url)
