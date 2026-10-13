"""Unified AI Gateway facade for Vault Personal Finance."""
from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from .circuit_breaker import CircuitBreakerManager
from .registry import NodeRegistry, ProviderRegistry
from .router import NodeRouter
from .types import GatewayResult, TaskType

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIGateway:
    """The central unified entry point for all AI model and agent invocations in Vault."""

    def __init__(self):
        self.circuit_breaker = CircuitBreakerManager()
        self.node_registry = NodeRegistry()
        self.router = NodeRouter(self.node_registry, self.circuit_breaker)
        self._initialized = False

    def initialize(self, force: bool = False):
        """Load nodes from environment / settings if not already loaded."""
        if not self._initialized or force:
            self.node_registry.load_from_environment()
            self._initialized = True

    def is_available(self, task: TaskType = TaskType.GENERAL) -> bool:
        """Check if at least one healthy node is configured and available for this task."""
        self.initialize()
        for node, key in self.router.plan_execution_nodes(task=task):
            if bool(key) or bool(node.base_url):
                return True
        return False

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
        task: TaskType = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> GatewayResult:
        """Execute text generation with multi-node load balancing and automatic failover."""
        self.initialize()
        start_time = time.time()
        attempted_errors: list[str] = []
        fallback_used = False
        first_node_id: str | None = None

        for node, active_key in self.router.plan_execution_nodes(task=task, preferred_node_id=preferred_node_id):
            if first_node_id is None:
                first_node_id = node.id
            elif node.id != first_node_id:
                fallback_used = True

            adapter = ProviderRegistry.get(node.provider)
            if not adapter:
                logger.warning("No adapter registered for provider '%s' on node '%s'", node.provider, node.id)
                continue

            target_model = model or node.get_model_for_task(task)

            try:
                logger.debug(
                    "Routing %s to node '%s' (%s, model '%s', key '%s')",
                    task.value, node.id, node.provider, target_model, node.get_masked_key()
                )
                text = adapter.generate_text(
                    node=node,
                    prompt=prompt,
                    system=system,
                    model=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=active_key,
                    **kwargs,
                )
                self.circuit_breaker.record_success(node)
                latency = (time.time() - start_time) * 1000.0

                return GatewayResult(
                    node_id=node.id,
                    provider=node.provider,
                    model=target_model,
                    content=text,
                    raw_text=text,
                    task=task,
                    latency_ms=latency,
                    fallback_used=fallback_used,
                )
            except Exception as e:
                err_str = str(e)
                logger.warning("Attempt on node '%s' failed: %s", node.id, err_str)
                attempted_errors.append(f"[{node.id}] {err_str}")

                if "429" in err_str or "rate limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self.circuit_breaker.record_key_rate_limit(node, active_key, cooldown_seconds=60.0)
                else:
                    self.circuit_breaker.record_failure(node, e)

        raise RuntimeError(
            f"All AI nodes failed for task '{task.value}'. Attempted {len(attempted_errors)} node(s):\n"
            + "\n".join(attempted_errors)
        )

    def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system: str | None = None,
        task: TaskType = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute structured JSON generation with Pydantic validation and automatic failover."""
        self.initialize()
        attempted_errors: list[str] = []

        for node, active_key in self.router.plan_execution_nodes(task=task, preferred_node_id=preferred_node_id):
            adapter = ProviderRegistry.get(node.provider)
            if not adapter:
                logger.warning("No adapter registered for provider '%s' on node '%s'", node.provider, node.id)
                continue

            target_model = model or node.get_model_for_task(task)

            try:
                logger.debug(
                    "Routing structured %s to node '%s' (%s, model '%s')",
                    task.value, node.id, node.provider, target_model
                )
                structured_obj = adapter.generate_structured(
                    node=node,
                    schema=schema,
                    prompt=prompt,
                    system=system,
                    model=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=active_key,
                    **kwargs,
                )
                self.circuit_breaker.record_success(node)
                return structured_obj
            except Exception as e:
                err_str = str(e)
                logger.warning("Structured generation failed on node '%s': %s", node.id, err_str)
                attempted_errors.append(f"[{node.id}] {err_str}")

                if "429" in err_str or "rate limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self.circuit_breaker.record_key_rate_limit(node, active_key, cooldown_seconds=60.0)
                else:
                    self.circuit_breaker.record_failure(node, e)

        raise RuntimeError(
            f"All AI nodes failed structured generation for task '{task.value}'. Attempted:\n"
            + "\n".join(attempted_errors)
        )

    def fetch_macro_grounding(self, prompt: str, **kwargs: Any) -> dict | None:
        """Fetch live macroeconomic indicators using search-grounded nodes."""
        self.initialize()
        for node, active_key in self.router.plan_execution_nodes(task=TaskType.RESEARCH):
            adapter = ProviderRegistry.get(node.provider)
            if not adapter:
                continue
            target_model = node.get_model_for_task(TaskType.RESEARCH)
            macro = adapter.fetch_macro_grounding(
                node=node,
                prompt=prompt,
                model=target_model,
                api_key=active_key,
                **kwargs,
            )
            if macro:
                return macro
        return None


# Global singleton instance
gateway = AIGateway()
