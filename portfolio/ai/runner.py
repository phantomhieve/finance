"""Unified AI analysis execution runner supporting Multi-Stage DAG and fallback engines."""
from __future__ import annotations

import json
import logging
import os

from django.conf import settings

from pftracker.ai_gateway import TaskType, gateway
from .builder import _DecimalEncoder
from .prompts import _MACRO_PROMPT, get_system_instruction
from .schemas import PortfolioInsightsResponse

logger = logging.getLogger(__name__)


class AIResult:
    """Standardized result wrapper for AI portfolio insights."""

    def __init__(self, model: str, insights_dict: dict):
        self.model = model
        self.insights_dict = insights_dict


# Backwards compatibility alias
GeminiResult = AIResult


def _fetch_macro_context(client=None) -> dict | None:
    """Fetch live Indian market macroeconomic context using Google Search grounding."""
    try:
        macro = gateway.fetch_macro_grounding(_MACRO_PROMPT)
        if macro:
            return macro
    except Exception as e:
        logger.debug("Gateway macro grounding failed: %s", e)
    return None


def call_shakti(prompt_data: dict, group=None) -> AIResult:
    """Call Shakti Cloud OpenAI-compatible endpoint with portfolio data and return structured insights.

    Uses streaming response accumulation to ensure network resilience against cloud/proxy timeouts.
    Employs a 2-stage DAG: Stage 1 performs deep reasoning via DeepSeek-R1; if direct parsing
    encounters formatting anomalies, Stage 2 uses an AI Structurer to extract compliant JSON.
    """
    from pftracker.ai_gateway import AINode
    from pftracker.ai_gateway.adapters.openai_compat import OpenAICompatibleAdapter

    api_key = os.environ.get('SHAKTI_API_KEY') or getattr(settings, 'SHAKTI_API_KEY', '')
    if not api_key:
        raise ValueError('SHAKTI_API_KEY environment variable is not set')

    base_url = (
        os.environ.get('SHAKTI_BASE_URL')
        or getattr(settings, 'SHAKTI_BASE_URL', 'https://http.prod-llm.shaktistudio.shakticloud.ai')
    ).strip().rstrip('/')
    client_id = (
        os.environ.get('SHAKTI_CLIENT_ID')
        or getattr(settings, 'SHAKTI_CLIENT_ID', '')
    )
    model = os.environ.get('SHAKTI_MODEL') or getattr(settings, 'SHAKTI_MODEL', 'deepseek-r1')
    max_tokens = int(os.environ.get('SHAKTI_MAX_TOKENS') or getattr(settings, 'SHAKTI_MAX_TOKENS', 8192))
    timeout_sec = float(os.environ.get('SHAKTI_TIMEOUT') or getattr(settings, 'SHAKTI_TIMEOUT', 300.0))
    temperature = float(os.environ.get('SHAKTI_TEMPERATURE') or getattr(settings, 'SHAKTI_TEMPERATURE', 0.1))
    max_retries = int(os.environ.get('SHAKTI_MAX_RETRIES') or getattr(settings, 'SHAKTI_MAX_RETRIES', 3))

    node = AINode(
        id="shakti-direct",
        provider="openai_compatible",
        base_url=base_url,
        api_keys=[api_key],
        default_model=model,
        headers={"id": client_id} if client_id else {},
        timeout=timeout_sec,
        max_retries=max_retries,
    )

    system_instruction = get_system_instruction(group)
    user_message = (
        "Analyze this portfolio. Use the data below and macro_context. "
        "Generate 8-12 insights across at least 5 categories.\n\n"
        f"Portfolio Data:\n{json.dumps(prompt_data, cls=_DecimalEncoder, indent=2)}"
    )

    adapter = OpenAICompatibleAdapter()
    parsed = adapter.generate_structured(
        node=node,
        schema=PortfolioInsightsResponse,
        prompt=user_message,
        system=system_instruction,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        stream=True,
    )

    return AIResult(
        model=f"shakti:{model}",
        insights_dict=parsed.model_dump(mode='json'),
    )


def call_gemini_direct(prompt_data: dict, group=None) -> AIResult:
    """Call Google Gemini with portfolio data and return structured insights."""
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError('GEMINI_API_KEY environment variable is not set')

    from pftracker.ai_gateway import AINode
    from pftracker.ai_gateway.adapters.gemini import GeminiAdapter

    model = (
        getattr(settings, "GEMINI_MODEL", "")
        or os.environ.get("GEMINI_MODEL", "")
        or ("gemini-3.5-flash-lite" if getattr(settings, "DEBUG", True) else "gemini-3.1-pro-preview")
    )
    logger.info("Calling Gemini model: %s", model)

    node = AINode(
        id="gemini-direct",
        provider="gemini",
        api_keys=[api_key],
        default_model=model,
    )

    macro = _fetch_macro_context()
    if macro:
        prompt_data['macro_context'] = macro

    system_instruction = get_system_instruction(group)
    user_message = (
        "Analyze this portfolio. Use the data below and macro_context. "
        "Generate 8-15 insights across at least 5 categories.\n\n"
        f"Portfolio Data:\n{json.dumps(prompt_data, cls=_DecimalEncoder, indent=2)}"
    )

    adapter = GeminiAdapter()
    parsed = adapter.generate_structured(
        node=node,
        schema=PortfolioInsightsResponse,
        prompt=user_message,
        system=system_instruction,
        model=model,
        api_key=api_key,
        temperature=0.3,
    )

    return AIResult(
        model=model,
        insights_dict=parsed.model_dump(mode='json'),
    )


def call_ai_insights(prompt_data: dict, group=None) -> AIResult:
    """Unified entry point for AI portfolio analysis and financial scoring.

    Selects provider based on settings.AI_PROVIDER ('shakti' or 'gemini'),
    with automatic multi-node routing and failover via Vault AI Gateway.
    """
    shakti_key = os.environ.get('SHAKTI_API_KEY') or getattr(settings, 'SHAKTI_API_KEY', '')
    gemini_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', '')
    if not shakti_key and not gemini_key and not gateway.is_available(TaskType.REASONING):
        raise ValueError("Neither SHAKTI_API_KEY nor GEMINI_API_KEY is configured")

    provider = (
        getattr(settings, 'AI_PROVIDER', '').lower()
        or os.environ.get('AI_PROVIDER', '').lower()
        or ('shakti' if shakti_key else 'gemini')
    )

    # 1. Fetch live macro context if available
    if 'macro_context' not in prompt_data:
        macro = _fetch_macro_context()
        if macro:
            prompt_data['macro_context'] = macro

    # 2. Multi-Stage DAG Execution (preferred engine)
    enable_dag = getattr(settings, 'ENABLE_PORTFOLIO_DAG', True)
    if enable_dag:
        try:
            from ..dag import run_portfolio_insights_dag
            return run_portfolio_insights_dag(prompt_data, group=group)
        except Exception as dag_err:
            logger.warning(
                "Multi-stage Portfolio DAG execution encountered issue (%s); falling back to single-shot generation...",
                dag_err,
            )

    # 3. Single-shot analysis fallback with structured output
    user_message = (
        "Analyze this portfolio. Use the data below and macro_context. "
        "Generate 8-15 insights across at least 5 categories.\n\n"
        f"Portfolio Data:\n{json.dumps(prompt_data, cls=_DecimalEncoder, indent=2)}"
    )

    try:
        parsed = gateway.generate_structured(
            schema=PortfolioInsightsResponse,
            prompt=user_message,
            system=get_system_instruction(group),
            task=TaskType.REASONING,
            temperature=0.2,
        )
        return AIResult(
            model=f"{provider}:insights",
            insights_dict=parsed.model_dump(mode='json'),
        )
    except Exception as gw_err:
        logger.warning("Gateway structured execution failed (%s); falling back to direct provider...", gw_err)
        if provider == 'shakti':
            if gemini_key:
                return call_gemini_direct(prompt_data, group=group)
            return call_shakti(prompt_data, group=group)
        elif provider == 'gemini':
            if shakti_key:
                return call_shakti(prompt_data, group=group)
            return call_gemini_direct(prompt_data, group=group)
        raise


# Alias call_gemini to call_ai_insights for backward compatibility with existing callers
call_gemini = call_ai_insights
