"""Type definitions and data structures for the Vault AI Gateway."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class TaskType(str, enum.Enum):
    """Semantic task tiers for AI routing."""
    FAST = "fast"                 # High-throughput, low-latency (categorisation, extraction, short notes)
    REASONING = "reasoning"       # Deep analytical reasoning (portfolio review, multi-pillar scoring)
    RESEARCH = "research"         # Grounded market intelligence (web search grounding, live macro indicators)
    EXTRACTION = "extraction"     # Document/statement/email parsing
    GENERAL = "general"           # Standard completion


class CircuitState(str, enum.Enum):
    """Circuit breaker states for nodes and keys."""
    CLOSED = "closed"       # Healthy, accepting traffic
    OPEN = "open"           # Cooling down after failures, traffic diverted
    HALF_OPEN = "half_open" # Testing node recovery with a canary request


@dataclass
class AINode:
    """Represents an execution endpoint (cloud provider, cluster, or self-hosted server)."""
    id: str
    provider: str                               # e.g., 'openai_compatible', 'gemini', 'anthropic'
    base_url: str | None = None                 # HTTP endpoint for node
    api_keys: list[str] = field(default_factory=list) # Pool of keys for this node
    default_model: str = ""                     # Model identifier on this node
    model_overrides: dict[TaskType, str] = field(default_factory=dict) # Optional per-task model mapping
    headers: dict[str, str] = field(default_factory=dict) # Custom HTTP headers (e.g., {"id": client_id})
    priority: int = 1                           # Lower number = higher priority (1 = primary tier, 2 = fallback)
    weight: int = 1                             # Weight for round-robin within the same priority tier
    timeout: float = 60.0                       # Request timeout in seconds
    max_retries: int = 2                        # Retries before marking node unhealthy
    cooldown_seconds: float = 60.0              # Seconds to stay in OPEN state before testing recovery
    supported_tasks: list[TaskType] = field(default_factory=lambda: list(TaskType))
    is_active: bool = True

    def get_model_for_task(self, task: TaskType) -> str:
        """Resolve the model name for a specific task tier."""
        if task in self.model_overrides and self.model_overrides[task]:
            return self.model_overrides[task]
        return self.default_model

    def get_masked_key(self, key_index: int = 0) -> str:
        """Return safe masked representation of an API key."""
        if not self.api_keys or key_index >= len(self.api_keys):
            return "[NO_KEY]"
        key = self.api_keys[key_index]
        if len(key) <= 8:
            return "[SET]"
        return f"{key[:4]}...{key[-4:]}"


@dataclass
class GatewayResult:
    """Standardized response from the AI Gateway."""
    node_id: str
    provider: str
    model: str
    content: Any                          # String for text, BaseModel/dict for structured
    raw_text: str = ""
    task: TaskType = TaskType.GENERAL
    latency_ms: float = 0.0
    fallback_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
