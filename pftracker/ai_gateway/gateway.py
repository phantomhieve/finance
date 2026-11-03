"""Unified AI Gateway facade for Vault Personal Finance."""
from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from .circuit_breaker import CircuitBreakerManager
from .config import ResolvedTaskConfig, TaskProfile, ai_config
from .registry import NodeRegistry, ProviderRegistry
from .router import NodeRouter
from .sanitizer import mask_pii, mask_secrets
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

    def _resolve_task_params(
        self,
        task: TaskProfile | TaskType | str,
        model: str | None,
        temperature: float | None,
        preferred_node_id: str | None,
        max_tokens: int | None,
        kwargs: dict[str, Any],
    ) -> tuple[TaskType, str | None, float, str | None, int | None, dict[str, Any]]:
        """Resolve model, temperature, thinking config, and node from TaskProfile or fallbacks."""
        resolved: ResolvedTaskConfig = ai_config.resolve(
            task=task,
            model_override=model,
            temperature_override=temperature,
        )

        target_task_type = resolved.task_type
        target_model = model or resolved.model
        target_temp = temperature if temperature is not None else resolved.temperature
        target_node_id = preferred_node_id or resolved.preferred_node_id
        target_max_tokens = max_tokens or resolved.max_tokens

        # Pass through or default thinking config
        if "thinking_level" not in kwargs and resolved.thinking_level is not None:
            kwargs["thinking_level"] = resolved.thinking_level
        if "thinking_budget" not in kwargs and resolved.thinking_budget is not None:
            kwargs["thinking_budget"] = resolved.thinking_budget

        return target_task_type, target_model, target_temp, target_node_id, target_max_tokens, kwargs

    def is_available(self, task: TaskProfile | TaskType | str = TaskType.GENERAL) -> bool:
        """Check if at least one healthy node is configured and available for this task."""
        self.initialize()
        task_type = task if isinstance(task, TaskType) else ai_config.resolve(task).task_type
        for node, key in self.router.plan_execution_nodes(task=task_type):
            if bool(key) or bool(node.base_url):
                return True
        return False

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
        task: TaskProfile | TaskType | str = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        sanitize_input: bool | None = None,
        **kwargs: Any,
    ) -> GatewayResult:
        """Execute text generation with multi-node load balancing and automatic failover."""
        self.initialize()

        # 1. Resolve task configuration parameters
        (
            task_type,
            target_model,
            temperature,
            preferred_node_id,
            max_tokens,
            kwargs,
        ) = self._resolve_task_params(
            task=task,
            model=model,
            temperature=temperature,
            preferred_node_id=preferred_node_id,
            max_tokens=max_tokens,
            kwargs=kwargs,
        )

        # 2. Privacy & PII scrubbing
        resolved_spec = ai_config.resolve(task)
        should_sanitize = sanitize_input if sanitize_input is not None else resolved_spec.sanitize_input
        if should_sanitize:
            prompt = mask_pii(prompt)
            if system:
                system = mask_pii(system)

        if preferred_node_id is None and target_model:
            m_low = target_model.lower()
            if any(m_low.startswith(p) for p in ("gemini", "argon", "flash")):
                preferred_node_id = "gemini-cloud"
            elif any(m_low.startswith(p) for p in ("deepseek", "llama", "shakti")):
                preferred_node_id = "shakti-primary"

        start_time = time.time()
        attempted_errors: list[str] = []
        fallback_used = False
        first_node_id: str | None = None

        for node, active_key in self.router.plan_execution_nodes(task=task_type, preferred_node_id=preferred_node_id):
            if first_node_id is None:
                first_node_id = node.id
            elif node.id != first_node_id:
                fallback_used = True

            adapter = ProviderRegistry.get(node.provider)
            if not adapter:
                logger.warning("No adapter registered for provider '%s' on node '%s'", node.provider, node.id)
                continue

            exec_model = target_model or node.get_model_for_task(task_type)

            try:
                logger.debug(
                    "Routing %s to node '%s' (%s, model '%s', key '%s')",
                    task_type.value, node.id, node.provider, exec_model, node.get_masked_key()
                )
                text = adapter.generate_text(
                    node=node,
                    prompt=prompt,
                    system=system,
                    model=exec_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=active_key,
                    task=task_type,
                    **kwargs,
                )
                self.circuit_breaker.record_success(node)
                latency = (time.time() - start_time) * 1000.0

                return GatewayResult(
                    node_id=node.id,
                    provider=node.provider,
                    model=exec_model,
                    content=text,
                    raw_text=text,
                    task=task_type,
                    latency_ms=latency,
                    fallback_used=fallback_used,
                )
            except Exception as e:
                err_str = mask_secrets(str(e))
                logger.warning("Attempt on node '%s' failed: %s", node.id, err_str)
                attempted_errors.append(f"[{node.id}] {err_str}")

                if "429" in err_str or "rate limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self.circuit_breaker.record_key_rate_limit(node, active_key, cooldown_seconds=60.0)
                else:
                    self.circuit_breaker.record_failure(node, e)

        raise RuntimeError(
            mask_secrets(
                f"All AI nodes failed for task '{task_type.value}'. Attempted {len(attempted_errors)} node(s):\n"
                + "\n".join(attempted_errors)
            )
        )

    def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system: str | None = None,
        task: TaskProfile | TaskType | str = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        sanitize_input: bool | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute structured JSON generation with Pydantic validation and automatic failover."""
        self.initialize()

        # 1. Resolve task configuration parameters
        (
            task_type,
            target_model,
            temperature,
            preferred_node_id,
            max_tokens,
            kwargs,
        ) = self._resolve_task_params(
            task=task,
            model=model,
            temperature=temperature,
            preferred_node_id=preferred_node_id,
            max_tokens=max_tokens,
            kwargs=kwargs,
        )

        # 2. Privacy & PII scrubbing
        resolved_spec = ai_config.resolve(task)
        should_sanitize = sanitize_input if sanitize_input is not None else resolved_spec.sanitize_input
        if should_sanitize:
            prompt = mask_pii(prompt)
            if system:
                system = mask_pii(system)

        if preferred_node_id is None and target_model:
            m_low = target_model.lower()
            if any(m_low.startswith(p) for p in ("gemini", "argon", "flash")):
                preferred_node_id = "gemini-cloud"
            elif any(m_low.startswith(p) for p in ("deepseek", "llama", "shakti")):
                preferred_node_id = "shakti-primary"

        attempted_errors: list[str] = []

        for node, active_key in self.router.plan_execution_nodes(task=task_type, preferred_node_id=preferred_node_id):
            adapter = ProviderRegistry.get(node.provider)
            if not adapter:
                logger.warning("No adapter registered for provider '%s' on node '%s'", node.provider, node.id)
                continue

            exec_model = target_model or node.get_model_for_task(task_type)

            try:
                logger.debug(
                    "Routing structured %s to node '%s' (%s, model '%s')",
                    task_type.value, node.id, node.provider, exec_model
                )
                structured_obj = adapter.generate_structured(
                    node=node,
                    schema=schema,
                    prompt=prompt,
                    system=system,
                    model=exec_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=active_key,
                    task=task_type,
                    **kwargs,
                )
                self.circuit_breaker.record_success(node)
                return structured_obj
            except Exception as e:
                err_str = mask_secrets(str(e))
                logger.warning("Structured generation failed on node '%s': %s", node.id, err_str)
                attempted_errors.append(f"[{node.id}] {err_str}")

                if "429" in err_str or "rate limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self.circuit_breaker.record_key_rate_limit(node, active_key, cooldown_seconds=60.0)
                else:
                    self.circuit_breaker.record_failure(node, e)

        raise RuntimeError(
            mask_secrets(
                f"All AI nodes failed structured generation for task '{task_type.value}'. Attempted:\n"
                + "\n".join(attempted_errors)
            )
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

    async def agenerate_text(
        self,
        prompt: str,
        system: str | None = None,
        task: TaskProfile | TaskType | str = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        sanitize_input: bool | None = None,
        **kwargs: Any,
    ) -> GatewayResult:
        """Asynchronously generate text without blocking the event loop."""
        from pftracker.concurrency import safe_async_to_thread

        return await safe_async_to_thread(
            self.generate_text,
            prompt=prompt,
            system=system,
            task=task,
            preferred_node_id=preferred_node_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            sanitize_input=sanitize_input,
            **kwargs,
        )

    async def agenerate_structured(
        self,
        schema: type[T],
        prompt: str,
        system: str | None = None,
        task: TaskProfile | TaskType | str = TaskType.GENERAL,
        preferred_node_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        sanitize_input: bool | None = None,
        **kwargs: Any,
    ) -> T:
        """Asynchronously generate structured output validated against Pydantic schema."""
        from pftracker.concurrency import safe_async_to_thread

        return await safe_async_to_thread(
            self.generate_structured,
            schema=schema,
            prompt=prompt,
            system=system,
            task=task,
            preferred_node_id=preferred_node_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            sanitize_input=sanitize_input,
            **kwargs,
        )


# Global singleton instance
gateway = AIGateway()
