"""OpenAI-compatible provider adapter supporting Shakti Cloud, local vLLM/Ollama nodes, and OpenAI."""
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


class OpenAICompatibleAdapter(BaseAIAdapter):
    """Adapter for any OpenAI-compatible API endpoint (Shakti Cloud, vLLM, Ollama, DeepSeek, etc.)."""

    def _get_client(self, node: AINode, api_key: str | None = None):
        from openai import OpenAI

        key = api_key or (node.api_keys[0] if node.api_keys else "none")
        base_url = node.base_url.rstrip("/") if node.base_url else None
        headers = dict(node.headers) if node.headers else None

        return OpenAI(
            api_key=key,
            base_url=base_url,
            default_headers=headers,
            timeout=node.timeout,
        )

    def generate_text(
        self,
        node: AINode,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        api_key: str | None = None,
        stream: bool = True,
        **kwargs: Any,
    ) -> str:
        client = self._get_client(node, api_key=api_key)
        target_model = model or node.default_model

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        create_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            create_kwargs["max_tokens"] = max_tokens

        if stream:
            # Accumulate streaming chunks to prevent intermediate proxy disconnects
            response = client.chat.completions.create(stream=True, **create_kwargs)
            chunks = []
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta:
                    content = chunk.choices[0].delta.content or ""
                    chunks.append(content)
            return "".join(chunks).strip()
        else:
            response = client.chat.completions.create(stream=False, **create_kwargs)
            return (response.choices[0].message.content or "").strip()

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
        stream: bool = True,
        **kwargs: Any,
    ) -> T:
        """Generate structured Pydantic object with automatic 2-stage DAG fallback."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        json_instruction = (
            "\n\nCRITICAL OUTPUT FORMAT INSTRUCTION:\n"
            "You MUST reply with ONLY a single valid, parseable JSON object adhering to this schema:\n"
            f"{schema_json}\n\n"
            "Do NOT include markdown fences (```json), do not include <think> tags, and do not include extra text. "
            "Start your reply directly with { and end with }."
        )
        effective_system = (system or "") + json_instruction

        # Stage 1: Generate response
        raw_text = self.generate_text(
            node=node,
            prompt=prompt,
            system=effective_system,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens or 8192,
            api_key=api_key,
            stream=stream,
            **kwargs,
        )

        cleaned = clean_json_text(raw_text)

        # Attempt direct validation
        try:
            return schema.model_validate_json(cleaned)
        except Exception as stage1_err:
            logger.warning(
                "Node '%s' Direct JSON validation failed (%s); triggering Stage 2 DAG Structurer...",
                node.id, stage1_err
            )
            # Stage 2: DAG AI Structurer fallback
            try:
                structured_data = self._stage2_dag_structure(
                    node=node,
                    schema=schema,
                    raw_text=raw_text,
                    api_key=api_key,
                )
                logger.info("Successfully structured output via Stage 2 DAG AI Structurer!")
                return structured_data
            except Exception as stage2_err:
                logger.error(
                    "Both direct parsing and Stage 2 DAG Structurer failed for node '%s': %s | Stage 1 error: %s",
                    node.id, stage2_err, stage1_err
                )
                raise RuntimeError(
                    f"Failed to generate structured data from node '{node.id}': {stage2_err}"
                ) from stage2_err

    def _stage2_dag_structure(
        self,
        node: AINode,
        schema: type[T],
        raw_text: str,
        api_key: str | None = None,
    ) -> T:
        """Stage 2 DAG: Reshapes raw reasoning text into the target Pydantic schema using 0.0 temperature."""
        client = self._get_client(node, api_key=api_key)
        schema_json = json.dumps(schema.model_json_schema(), indent=2)

        structurer_system = (
            "You are an expert data structuring engine. "
            "Convert the provided analysis text into a single, valid JSON object strictly matching this schema:\n"
            f"{schema_json}\n\n"
            "Rules:\n"
            "1. Extract all facts, numbers, and decisions faithfully from the text. Do not invent facts.\n"
            "2. Output ONLY valid JSON starting with { and ending with }. No code fences, no extra commentary."
        )

        response = client.chat.completions.create(
            model=node.default_model,
            messages=[
                {"role": "system", "content": structurer_system},
                {"role": "user", "content": f"Extract and format structured JSON from this text:\n\n{raw_text}"},
            ],
            max_tokens=8192,
            temperature=0.0,
            stream=False,
        )
        content = response.choices[0].message.content or ""
        cleaned = clean_json_text(content)
        return schema.model_validate_json(cleaned)
