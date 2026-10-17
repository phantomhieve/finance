"""AI-powered portfolio analysis package for Vault Personal Finance.

Modularized architecture:
  - portfolio.ai.schemas: Pydantic response models, insight models, and enums.
  - portfolio.ai.prompts: System instructions, investor profile loaders, macro prompts.
  - portfolio.ai.builder: Structured portfolio data builders and serializers.
  - portfolio.ai.runner: Multi-Stage DAG and single-shot execution orchestrator.
"""
from __future__ import annotations

from pftracker.ai_gateway import clean_json_text as _clean_json_text  # noqa: F401 — re-exported for backwards compatibility

from .builder import (
    _ACTIVE_SIP_THRESHOLD,
    _DecimalEncoder,
    _holding_entry,
    build_prompt_data,
)
from .prompts import (
    _MACRO_PROMPT,
    SYSTEM_INSTRUCTION,
    _investor_profile_path,
    _load_investor_profile,
    get_system_instruction,
)
from .runner import (
    AIResult,
    GeminiResult,
    _fetch_macro_context,
    call_ai_insights,
    call_gemini,
    call_gemini_direct,
    call_shakti,
)
from .schemas import (
    Insight,
    InsightCategory,
    InsightSeverity,
    PortfolioInsightsResponse,
)

__all__ = [
    # Schemas
    "InsightCategory",
    "InsightSeverity",
    "Insight",
    "PortfolioInsightsResponse",
    # Prompts & Profile
    "SYSTEM_INSTRUCTION",
    "_MACRO_PROMPT",
    "_investor_profile_path",
    "_load_investor_profile",
    "get_system_instruction",
    # Data Builder
    "_DecimalEncoder",
    "_ACTIVE_SIP_THRESHOLD",
    "_holding_entry",
    "build_prompt_data",
    # Execution Runner
    "AIResult",
    "GeminiResult",
    "call_ai_insights",
    "call_gemini",
    "call_shakti",
    "call_gemini_direct",
    "_fetch_macro_context",
    # Utilities
    "_clean_json_text",
]
