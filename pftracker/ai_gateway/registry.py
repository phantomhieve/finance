"""Dynamic registries for AI provider adapters and multi-node topologies."""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from django.conf import settings

from .adapters import BaseAIAdapter, GeminiAdapter, OpenAICompatibleAdapter
from .types import AINode, TaskType

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry of adapter implementations by provider name."""
    _adapters: dict[str, BaseAIAdapter] = {}

    @classmethod
    def register(cls, name: str, adapter: BaseAIAdapter):
        cls._adapters[name.lower()] = adapter

    @classmethod
    def get(cls, name: str) -> BaseAIAdapter | None:
        return cls._adapters.get(name.lower())

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._adapters.keys())


# Register default adapters
ProviderRegistry.register("gemini", GeminiAdapter())
ProviderRegistry.register("openai_compatible", OpenAICompatibleAdapter())
ProviderRegistry.register("shakti", OpenAICompatibleAdapter())  # Convenience alias


class NodeRegistry:
    """Manages configured nodes and builds node topologies from settings and environment."""

    def __init__(self):
        self._nodes: dict[str, AINode] = {}

    def register(self, node: AINode):
        self._nodes[node.id] = node

    def get(self, node_id: str) -> AINode | None:
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[AINode]:
        return list(self._nodes.values())

    def get_nodes_for_task(self, task: TaskType) -> list[AINode]:
        return [
            node for node in self._nodes.values()
            if node.is_active and task in node.supported_tasks
        ]

    def load_from_environment(self):
        """Loads multi-node configuration using hybrid approach:

        1. If AI_NODES JSON is set, parses explicit node definitions.
        2. Otherwise parses standard/comma-separated env vars:
           - GEMINI_API_KEYS / GEMINI_API_KEY
           - SHAKTI_API_KEYS / SHAKTI_API_KEY
           - SHAKTI_BASE_URLS / SHAKTI_BASE_URL
        """
        self._nodes.clear()

        # 1. Check for structured JSON AI_NODES
        raw_json_nodes = getattr(settings, "AI_NODES", None) or os.environ.get("AI_NODES", "")
        if raw_json_nodes:
            try:
                parsed = json.loads(raw_json_nodes) if isinstance(raw_json_nodes, str) else raw_json_nodes
                for item in parsed:
                    keys = item.get("api_keys", [])
                    if isinstance(keys, str):
                        keys = [k.strip() for k in keys.split(",") if k.strip()]
                    node = AINode(
                        id=item["id"],
                        provider=item["provider"],
                        base_url=item.get("base_url"),
                        api_keys=keys,
                        default_model=item.get("default_model", ""),
                        headers=item.get("headers", {}),
                        priority=int(item.get("priority", 1)),
                        weight=int(item.get("weight", 1)),
                        timeout=float(item.get("timeout", 60.0)),
                        max_retries=int(item.get("max_retries", 2)),
                        cooldown_seconds=float(item.get("cooldown_seconds", 60.0)),
                    )
                    self.register(node)
                logger.info("Loaded %d AI nodes from AI_NODES configuration.", len(self._nodes))
                return
            except Exception as e:
                logger.warning("Failed to parse AI_NODES JSON configuration: %s. Falling back to env vars.", e)

        # 2. Build nodes from hybrid environment variables
        pref_provider = (
            getattr(settings, "AI_PROVIDER", "")
            or os.environ.get("AI_PROVIDER", "")
        ).lower()

        # --- Parse Shakti / OpenAI-Compatible Nodes ---
        raw_shakti_keys = (
            os.environ.get("SHAKTI_API_KEYS")
            or getattr(settings, "SHAKTI_API_KEYS", None)
            or os.environ.get("SHAKTI_API_KEY")
            or getattr(settings, "SHAKTI_API_KEY", "")
        )
        shakti_keys = [k.strip() for k in str(raw_shakti_keys).split(",") if k.strip()]

        raw_shakti_urls = (
            os.environ.get("SHAKTI_BASE_URLS")
            or getattr(settings, "SHAKTI_BASE_URLS", None)
            or os.environ.get("SHAKTI_BASE_URL")
            or getattr(settings, "SHAKTI_BASE_URL", "https://http.prod-llm.shaktistudio.shakticloud.ai")
        )
        shakti_urls = [u.strip() for u in str(raw_shakti_urls).split(",") if u.strip()]

        shakti_client_id = os.environ.get("SHAKTI_CLIENT_ID") or getattr(settings, "SHAKTI_CLIENT_ID", "")
        shakti_model = os.environ.get("SHAKTI_MODEL") or getattr(settings, "SHAKTI_MODEL", "deepseek-r1")
        shakti_timeout = float(os.environ.get("SHAKTI_TIMEOUT") or getattr(settings, "SHAKTI_TIMEOUT", 300.0))
        shakti_retries = int(os.environ.get("SHAKTI_MAX_RETRIES") or getattr(settings, "SHAKTI_MAX_RETRIES", 3))

        shakti_priority = 1 if pref_provider == "shakti" or not pref_provider else 2

        for idx, base_url in enumerate(shakti_urls):
            node_id = f"shakti-node-{idx + 1}" if len(shakti_urls) > 1 else "shakti-primary"
            node = AINode(
                id=node_id,
                provider="openai_compatible",
                base_url=base_url,
                api_keys=shakti_keys,
                default_model=shakti_model,
                model_overrides={
                    TaskType.REASONING: shakti_model,
                    TaskType.FAST: shakti_model,
                },
                headers={"id": shakti_client_id} if shakti_client_id else {},
                priority=shakti_priority,
                timeout=shakti_timeout,
                max_retries=shakti_retries,
            )
            self.register(node)

        # --- Parse Gemini Nodes ---
        raw_gemini_keys = (
            os.environ.get("GEMINI_API_KEYS")
            or getattr(settings, "GEMINI_API_KEYS", None)
            or os.environ.get("GEMINI_API_KEY")
            or getattr(settings, "GEMINI_API_KEY", "")
        )
        gemini_keys = [k.strip() for k in str(raw_gemini_keys).split(",") if k.strip()]

        is_debug = getattr(settings, "DEBUG", True)
        gemini_model_prod = (
            getattr(settings, "GEMINI_MODEL", "")
            or os.environ.get("GEMINI_MODEL", "")
            or ("gemini-3.8-flash" if is_debug else "gemini-4-argon")
        )
        if gemini_model_prod.strip().lower() in ("argon", "gemini-argon", "gemini_argon"):
            gemini_model_prod = "gemini-4-argon"
        elif gemini_model_prod.strip().lower() in ("flash", "gemini-flash", "3.8-flash", "gemini-3.8-flash"):
            gemini_model_prod = "gemini-3.8-flash"

        gemini_model_fast = (
            getattr(settings, "EXPENSES_GEMINI_MODEL", "")
            or os.environ.get("EXPENSES_GEMINI_MODEL", "")
            or "gemini-3.8-flash"
        )
        if gemini_model_fast.strip().lower() in ("argon", "gemini-argon", "gemini_argon"):
            gemini_model_fast = "gemini-4-argon"
        elif gemini_model_fast.strip().lower() in ("flash", "gemini-flash", "3.8-flash", "gemini-3.8-flash"):
            gemini_model_fast = "gemini-3.8-flash"

        gemini_priority = 1 if pref_provider == "gemini" else 2

        if gemini_keys:
            gemini_node = AINode(
                id="gemini-cloud",
                provider="gemini",
                api_keys=gemini_keys,
                default_model=gemini_model_prod,
                model_overrides={
                    TaskType.FAST: gemini_model_fast,
                    TaskType.EXTRACTION: gemini_model_fast,
                    TaskType.REASONING: gemini_model_prod,
                    TaskType.RESEARCH: gemini_model_fast,
                },
                priority=gemini_priority,
                timeout=60.0,
                max_retries=2,
            )
            self.register(gemini_node)

        logger.info("Initialized %d AI nodes from environment settings.", len(self._nodes))
