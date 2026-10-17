"""Circuit breaker and API key pool management for multi-node deployments."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from .types import AINode, CircuitState

logger = logging.getLogger(__name__)


@dataclass
class KeyState:
    """Tracks status of an individual API key."""
    key: str
    cooldown_until: float = 0.0
    failure_count: int = 0

    @property
    def is_cooling_down(self) -> bool:
        return time.time() < self.cooldown_until


@dataclass
class NodeRuntimeState:
    """Tracks runtime health metrics and key rotation state for an AINode."""
    node_id: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    cooldown_until: float = 0.0
    current_key_index: int = 0
    key_states: dict[str, KeyState] = field(default_factory=dict)
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0


class CircuitBreakerManager:
    """Thread-safe manager for node circuit breakers and key pools."""

    def __init__(self):
        self._lock = threading.Lock()
        self._node_states: dict[str, NodeRuntimeState] = {}

    def _get_or_create(self, node: AINode) -> NodeRuntimeState:
        if node.id not in self._node_states:
            st = NodeRuntimeState(node_id=node.id)
            for k in node.api_keys:
                st.key_states[k] = KeyState(key=k)
            self._node_states[node.id] = st
        else:
            st = self._node_states[node.id]
            # Ensure all keys in node definition are tracked
            for k in node.api_keys:
                if k not in st.key_states:
                    st.key_states[k] = KeyState(key=k)
        return self._node_states[node.id]

    def is_node_available(self, node: AINode) -> bool:
        """Check if a node is currently available for traffic."""
        if not node.is_active:
            return False

        with self._lock:
            st = self._get_or_create(node)
            now = time.time()

            if st.state == CircuitState.OPEN:
                if now >= st.cooldown_until:
                    # Transition to HALF_OPEN to test recovery with canary
                    st.state = CircuitState.HALF_OPEN
                    logger.info("Node '%s' circuit transitioning from OPEN to HALF_OPEN (probing recovery)", node.id)
                    return True
                return False
            return True

    def get_active_key(self, node: AINode) -> tuple[str, int]:
        """Get the next healthy API key from the node's key pool using round-robin.

        Returns (key_string, key_index). If no keys or all cooling down, returns ("", -1).
        """
        if not node.api_keys:
            return "", -1

        with self._lock:
            st = self._get_or_create(node)
            num_keys = len(node.api_keys)

            # Try up to num_keys starting from current_key_index
            for i in range(num_keys):
                candidate_idx = (st.current_key_index + i) % num_keys
                cand_key = node.api_keys[candidate_idx]
                k_state = st.key_states.get(cand_key)

                if k_state and not k_state.is_cooling_down:
                    st.current_key_index = (candidate_idx + 1) % num_keys
                    return cand_key, candidate_idx

            # If all are cooling down, return the one closest to expiry
            logger.warning("All %d API keys for node '%s' are cooling down!", num_keys, node.id)
            earliest_idx = 0
            earliest_time = float("inf")
            for idx, k in enumerate(node.api_keys):
                k_state = st.key_states.get(k)
                if k_state and k_state.cooldown_until < earliest_time:
                    earliest_time = k_state.cooldown_until
                    earliest_idx = idx

            return node.api_keys[earliest_idx], earliest_idx

    def record_key_rate_limit(self, node: AINode, key: str, cooldown_seconds: float = 60.0):
        """Put a specific rate-limited key (HTTP 429) on cooldown."""
        with self._lock:
            st = self._get_or_create(node)
            k_state = st.key_states.get(key)
            if not k_state:
                k_state = KeyState(key=key)
                st.key_states[key] = k_state

            k_state.cooldown_until = time.time() + cooldown_seconds
            k_state.failure_count += 1
            logger.warning(
                "API key [%s] on node '%s' placed on cooldown for %.1fs (HTTP 429 rate limit)",
                node.get_masked_key(node.api_keys.index(key) if key in node.api_keys else 0),
                node.id,
                cooldown_seconds,
            )

    def record_success(self, node: AINode):
        """Record a successful invocation, closing circuit if half-open."""
        with self._lock:
            st = self._get_or_create(node)
            st.total_requests += 1
            st.total_successes += 1
            st.consecutive_failures = 0

            if st.state == CircuitState.HALF_OPEN:
                st.state = CircuitState.CLOSED
                logger.info("Node '%s' canary request succeeded. Circuit CLOSED.", node.id)

    def record_failure(self, node: AINode, error: Exception):
        """Record an error, tripping the circuit to OPEN if threshold exceeded."""
        with self._lock:
            st = self._get_or_create(node)
            st.total_requests += 1
            st.total_failures += 1
            st.consecutive_failures += 1
            st.last_failure_time = time.time()

            if st.state == CircuitState.HALF_OPEN or st.consecutive_failures >= node.max_retries:
                st.state = CircuitState.OPEN
                st.cooldown_until = time.time() + node.cooldown_seconds
                logger.error(
                    "Node '%s' tripped circuit to OPEN for %.1fs after %d consecutive failure(s): %s",
                    node.id,
                    node.cooldown_seconds,
                    st.consecutive_failures,
                    error,
                )

    def get_status_summary(self) -> dict[str, dict]:
        """Return a snapshot of all node health states."""
        with self._lock:
            out = {}
            for node_id, st in self._node_states.items():
                out[node_id] = {
                    "state": st.state.value,
                    "consecutive_failures": st.consecutive_failures,
                    "total_requests": st.total_requests,
                    "total_successes": st.total_successes,
                    "total_failures": st.total_failures,
                    "cooling_down_until": round(st.cooldown_until, 1),
                }
            return out
