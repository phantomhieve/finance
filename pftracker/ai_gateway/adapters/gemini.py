"""Google GenAI provider adapter with native structured outputs and Search Grounding."""
from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from ..sanitizer import clean_json_text
from ..types import AINode
from .base import BaseAIAdapter

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiAdapter(BaseAIAdapter):
    """Adapter for Google Gemini using the google-genai SDK."""

    def _get_client(self, node: AINode, api_key: str | None = None):
        from google import genai
        key = api_key or (node.api_keys[0] if node.api_keys else "")
        if not key:
            raise ValueError(f"No API key provided for Gemini node '{node.id}'")
        return genai.Client(api_key=key)

    def generate_text(
        self,
        node: AINode,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> str:
        from google import genai

        client = self._get_client(node, api_key=api_key)
        target_model = model or node.default_model

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if system:
            config_kwargs["system_instruction"] = system
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens

        resp = client.models.generate_content(
            model=target_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(**config_kwargs),
        )
        return resp.text or ""

    def generate_structured(
        self,
        node: AINode,
        schema: type[T],
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> T:
        from google import genai

        client = self._get_client(node, api_key=api_key)
        target_model = model or node.default_model

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": temperature,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens

        resp = client.models.generate_content(
            model=target_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(**config_kwargs),
        )
        raw_text = resp.text or ""
        try:
            return schema.model_validate_json(raw_text)
        except Exception:
            # Fall back to sanitizer in case model returned extra fences
            cleaned = clean_json_text(raw_text)
            return schema.model_validate_json(cleaned)

    def fetch_macro_grounding(
        self,
        node: AINode,
        prompt: str,
        api_key: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict | None:
        """Fetch live macroeconomic context using Google Search grounding."""
        from google import genai

        client = self._get_client(node, api_key=api_key)
        target_model = model or node.default_model

        try:
            resp = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
                    temperature=0.1,
                ),
            )
            raw = (resp.text or "").strip()
            cleaned = clean_json_text(raw)
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("Failed to fetch macro grounding via Gemini: %s", e)
            return None
