"""Google GenAI provider adapter with native structured outputs and Search Grounding."""
from __future__ import annotations

import json
import logging
import socket
from typing import Any, TypeVar

from pydantic import BaseModel

from ..sanitizer import clean_json_text
from ..types import AINode
from .base import BaseAIAdapter

# Ensure IPv4 is preferred to prevent broken IPv6 network routes from causing 75s TCP SYN timeouts
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_preferred_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
    res = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in res if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else res

socket.getaddrinfo = _ipv4_preferred_getaddrinfo

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def _normalize_model_name(model: str | None) -> str:
    """Normalize user-friendly aliases like 'argon' to 'gemini-4-argon' and 'flash' to 'gemini-3.8-flash'."""
    if not model:
        return "gemini-4-argon"
    m = model.strip()
    m_lower = m.lower()
    if m_lower in ("argon", "gemini-argon", "gemini_argon"):
        return "gemini-4-argon"
    if m_lower in (
        "flash-lite",
        "flash_lite",
        "2.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini_2_5_flash_lite",
    ):
        return "gemini-2.5-flash-lite"
    if m_lower in (
        "flash",
        "gemini-flash",
        "gemini_flash",
        "3.8-flash",
        "gemini-3.8-flash",
        "gemini_3_8_flash",
        "3.5-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini_3_5_flash_lite",
    ):
        return "gemini-3.8-flash"
    return m



def _clean_schema_for_gemini(data: Any) -> Any:
    """Recursively strip 'additionalProperties' and unsupported schema keywords for Gemini API."""
    if isinstance(data, dict):
        return {
            k: _clean_schema_for_gemini(v)
            for k, v in data.items()
            if k not in ("additionalProperties", "$schema")
        }
    if isinstance(data, list):
        return [_clean_schema_for_gemini(item) for item in data]
    return data


def _build_gemini_thinking_config(
    model: str,
    task: Any = None,
    explicit_thinking_config: Any = None,
    thinking_level: Any = None,
    thinking_budget: Any = None,
) -> Any:
    """Resolve optimized ThinkingConfig for Gemini models based on dev vs prod and task tier.

    Optimization Matrix:
    - Portfolio (TaskType.REASONING):
      - PROD with Argon: ThinkingLevel.HIGH for exhaustive multi-pillar analysis.
      - DEV with Argon/Flash: ThinkingLevel.LOW for fast, iterative developer feedback.
    - Expenses (TaskType.FAST / EXTRACTION):
      - Both DEV and PROD: thinking_budget=0 (thinking disabled) for instantaneous
        extraction, matching, and categorisation without wasting latency or tokens.
    """
    import os
    from django.conf import settings
    from google import genai

    target = _normalize_model_name(model).lower()
    if "flash-lite" in target or "flash_lite" in target:
        return None

    # 1. Direct explicit ThinkingConfig takes highest precedence
    if explicit_thinking_config is not None:
        return explicit_thinking_config

    # 2. Check explicit keyword args or settings/env overrides
    cfg_level = thinking_level or getattr(settings, "GEMINI_THINKING_LEVEL", None) or os.environ.get("GEMINI_THINKING_LEVEL", "")
    cfg_budget = thinking_budget if thinking_budget is not None else getattr(settings, "GEMINI_THINKING_BUDGET", None)
    if cfg_budget is None and os.environ.get("GEMINI_THINKING_BUDGET"):
        try:
            cfg_budget = int(os.environ["GEMINI_THINKING_BUDGET"])
        except ValueError:
            cfg_budget = None

    level_enum = None
    if cfg_level:
        lvl_str = str(cfg_level).upper().strip()
        level_map = {
            "MINIMAL": genai.types.ThinkingLevel.MINIMAL,
            "LOW": genai.types.ThinkingLevel.LOW,
            "MEDIUM": genai.types.ThinkingLevel.MEDIUM,
            "HIGH": genai.types.ThinkingLevel.HIGH,
            "UNSPECIFIED": genai.types.ThinkingLevel.THINKING_LEVEL_UNSPECIFIED,
        }
        level_enum = level_map.get(lvl_str)

    if level_enum is not None or cfg_budget is not None:
        tc_kwargs: dict[str, Any] = {"include_thoughts": False}
        if level_enum is not None:
            tc_kwargs["thinking_level"] = level_enum
        if cfg_budget is not None:
            tc_kwargs["thinking_budget"] = cfg_budget
        return genai.types.ThinkingConfig(**tc_kwargs)

    # 3. Environment-aware automatic optimization
    target = _normalize_model_name(model).lower()
    is_reasoning_model = "argon" in target or "thinking" in target or "r1" in target
    is_debug = getattr(settings, "DEBUG", True)
    task_str = str(task.value if hasattr(task, "value") else (task or "")).lower()

    if is_reasoning_model:
        # Portfolio Analysis / Scoring / Fiduciary Review
        if task_str in ("reasoning", "research", ""):
            if is_debug:
                # DEV: Fast reasoning to keep development turnaround quick
                return genai.types.ThinkingConfig(
                    thinking_level=genai.types.ThinkingLevel.LOW,
                    include_thoughts=False,
                )
            else:
                # PROD: Exhaustive frontier reasoning across portfolio pillars
                return genai.types.ThinkingConfig(
                    thinking_level=genai.types.ThinkingLevel.HIGH,
                    include_thoughts=False,
                )
        # Expenses Tasks (Categorisation, Extraction, Receipt/Statement Parsing)
        elif task_str in ("fast", "extraction"):
            return genai.types.ThinkingConfig(
                thinking_budget=0,
                include_thoughts=False,
            )
    else:
        # Non-reasoning / Flash models:
        # In DEV, if running reasoning task on Flash:
        if task_str == "reasoning" and is_debug:
            return genai.types.ThinkingConfig(
                thinking_level=genai.types.ThinkingLevel.LOW,
                include_thoughts=False,
            )
        # Fast / extraction tasks on Flash:
        if task_str in ("fast", "extraction"):
            return genai.types.ThinkingConfig(
                thinking_budget=0,
                include_thoughts=False,
            )

    return None


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
        task: Any = None,
        **kwargs: Any,
    ) -> str:
        from google import genai

        client = self._get_client(node, api_key=api_key)
        target_model = _normalize_model_name(model or node.default_model)

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if system:
            config_kwargs["system_instruction"] = system
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens

        thinking_cfg = _build_gemini_thinking_config(
            model=target_model,
            task=task or kwargs.get("task"),
            explicit_thinking_config=kwargs.get("thinking_config"),
            thinking_level=kwargs.get("thinking_level"),
            thinking_budget=kwargs.get("thinking_budget"),
        )
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        try:
            resp = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            exc_str = str(exc).lower()
            if "thinking" in exc_str and ("not supported" in exc_str or "invalid" in exc_str):
                logger.warning("Gemini thinking_config not supported for model %s; retrying without it...", target_model)
                config_kwargs.pop("thinking_config", None)
                resp = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(**config_kwargs),
                )
            else:
                raise
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
        task: Any = None,
        **kwargs: Any,
    ) -> T:
        import json
        from google import genai

        client = self._get_client(node, api_key=api_key)
        target_model = _normalize_model_name(model or node.default_model)

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": temperature,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens

        thinking_cfg = _build_gemini_thinking_config(
            model=target_model,
            task=task or kwargs.get("task"),
            explicit_thinking_config=kwargs.get("thinking_config"),
            thinking_level=kwargs.get("thinking_level"),
            thinking_budget=kwargs.get("thinking_budget"),
        )
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        if hasattr(schema, "model_json_schema"):
            try:
                config_kwargs["response_schema"] = _clean_schema_for_gemini(schema.model_json_schema())
            except Exception:
                config_kwargs["response_schema"] = schema
        else:
            config_kwargs["response_schema"] = schema

        try:
            resp = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            exc_str = str(exc).lower()
            if "thinking" in exc_str and ("not supported" in exc_str or "invalid" in exc_str):
                logger.warning("Gemini thinking_config not supported for model %s; retrying without it...", target_model)
                config_kwargs.pop("thinking_config", None)
                resp = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(**config_kwargs),
                )
            elif "additionalproperties" in exc_str or "schema" in exc_str:
                logger.warning("Gemini response_schema failed (%s); retrying with JSON mode fallback...", exc)
                config_kwargs.pop("response_schema", None)
                schema_json = json.dumps(schema.model_json_schema()) if hasattr(schema, "model_json_schema") else ""
                fallback_prompt = (
                    f"{prompt}\n\nIMPORTANT: Output valid JSON matching this schema:\n{schema_json}"
                    if schema_json else prompt
                )
                resp = client.models.generate_content(
                    model=target_model,
                    contents=fallback_prompt,
                    config=genai.types.GenerateContentConfig(**config_kwargs),
                )
            else:
                raise

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
        target_model = _normalize_model_name(model or node.default_model)

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
