"""Multi-node routing, priority tiering, and failover orchestration."""
from __future__ import annotations

import logging
import threading
from typing import Iterator

from .circuit_breaker import CircuitBreakerManager
from .registry import NodeRegistry
from .types import AINode, TaskType

logger = logging.getLogger(__name__)


class NodeRouter:
    """Selects available nodes and key combinations across priority tiers with automatic failover."""

    def __init__(self, registry: NodeRegistry, circuit_breaker: CircuitBreakerManager):
        self._registry = registry
        self._circuit_breaker = circuit_breaker
        self._lock = threading.Lock()
        self._round_robin_indices: dict[int, int] = {}  # Priority tier -> index

    def plan_execution_nodes(
        self,
        task: TaskType = TaskType.GENERAL,
        preferred_node_id: str | None = None,
    ) -> Iterator[tuple[AINode, str]]:
        """Yields (node, active_api_key) candidates ordered by priority and health.

        If preferred_node_id is specified and available, attempts that node first.
        Otherwise groups healthy nodes by priority (1 = primary, 2 = secondary, etc.)
        and applies round-robin within each tier before cascading to subsequent tiers.
        """
        all_nodes = self._registry.list_nodes()
        if not all_nodes:
            logger.warning("No AI nodes are currently registered in the NodeRegistry.")
            return

        # 1. Handle explicit preferred node
        if preferred_node_id:
            target = self._registry.get(preferred_node_id)
            if target and target.is_active:
                key, _ = self._circuit_breaker.get_active_key(target)
                yield target, key
                return
            else:
                logger.warning("Preferred node '%s' not found or inactive. Falling back to pool.", preferred_node_id)

        # 2. Filter nodes supporting the given task
        eligible = [
            n for n in all_nodes
            if n.is_active and task in n.supported_tasks and self._circuit_breaker.is_node_available(n)
        ]

        if not eligible:
            # Fall back to any active node even if cooling down if desperate
            logger.warning("No healthy nodes available for task '%s'. Checking all active nodes.", task.value)
            eligible = [n for n in all_nodes if n.is_active and task in n.supported_tasks]

        if not eligible:
            return

        # 3. Group by priority tier
        tiers: dict[int, list[AINode]] = {}
        for n in eligible:
            tiers.setdefault(n.priority, []).append(n)

        # 4. Iterate tiers in ascending order of priority (1, 2, 3...)
        for priority in sorted(tiers.keys()):
            tier_nodes = tiers[priority]
            with self._lock:
                start_idx = self._round_robin_indices.get(priority, 0)
                # Rotate for next call
                self._round_robin_indices[priority] = (start_idx + 1) % len(tier_nodes)

            # Reorder tier nodes starting from start_idx
            ordered = [tier_nodes[(start_idx + i) % len(tier_nodes)] for i in range(len(tier_nodes))]

            for node in ordered:
                # Get healthy key from node's key pool
                key, _ = self._circuit_breaker.get_active_key(node)
                yield node, key
