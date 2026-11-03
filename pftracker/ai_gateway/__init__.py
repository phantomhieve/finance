"""Vault Unified AI Gateway for multi-node, multi-provider, multi-key AI execution."""
from .circuit_breaker import CircuitBreakerManager
from .config import (
    AIConfigRegistry,
    ResolvedTaskConfig,
    TaskProfile,
    TaskSpec,
    ai_config,
)
from .gateway import AIGateway, gateway
from .registry import NodeRegistry, ProviderRegistry
from .sanitizer import (
    clean_json_text,
    detect_prompt_injection,
    escape_xml_boundaries,
    mask_pii,
    mask_secrets,
    safe_json_loads,
    wrap_user_payload,
)
from .types import AINode, CircuitState, GatewayResult, TaskType

__all__ = [
    # Gateway facade & singletons
    "AIGateway",
    "gateway",
    "ai_config",
    # Types & Profiles
    "TaskType",
    "TaskProfile",
    "TaskSpec",
    "ResolvedTaskConfig",
    "AINode",
    "GatewayResult",
    "CircuitState",
    # Registries
    "ProviderRegistry",
    "NodeRegistry",
    "AIConfigRegistry",
    "CircuitBreakerManager",
    # Sanitization & Security
    "clean_json_text",
    "safe_json_loads",
    "mask_pii",
    "mask_secrets",
    "detect_prompt_injection",
    "wrap_user_payload",
    "escape_xml_boundaries",
]
