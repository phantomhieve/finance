"""Central Configuration Management for Vault AI Gateway.

Provides a declarative source of truth for all AI tasks, mapping each semantic task
to its dev vs. prod models, reasoning/thinking configurations, temperatures, token limits,
provider routing, and security/sanitization flags.
"""
from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from .types import TaskType

logger = logging.getLogger(__name__)


class TaskProfile(str, enum.Enum):
    """Canonical task profiles across Vault."""
    # Portfolio Intelligence & Scoring
    PORTFOLIO_INSIGHTS = "portfolio_insights"
    PORTFOLIO_DAG_ALLOCATION = "portfolio_dag_allocation"
    PORTFOLIO_DAG_QUALITY = "portfolio_dag_quality"
    PORTFOLIO_DAG_MACRO = "portfolio_dag_macro"
    PORTFOLIO_DAG_STRATEGY = "portfolio_dag_strategy"
    PORTFOLIO_DAG_SYNTHESIS = "portfolio_dag_synthesis"

    # Real Estate & Annual Appraisal
    LAND_APPRAISAL_COMPS = "land_appraisal_comps"
    LAND_APPRAISAL_AUDIT = "land_appraisal_audit"
    LAND_APPRAISAL_SYNTHESIS = "land_appraisal_synthesis"

    # Communication & Digest
    WEEKLY_BRIEF = "weekly_brief"
    MONTHLY_EXPENSE_NOTE = "monthly_expense_note"

    # Expenses Operations
    EXPENSE_CATEGORIZATION = "expense_categorization"
    RECEIPT_PARSING = "receipt_parsing"
    STATEMENT_PARSING = "statement_parsing"
    STATEMENT_MATCHING = "statement_matching"
    EXPENSE_ANOMALY = "expense_anomaly"


@dataclass(frozen=True)
class TaskSpec:
    """Declarative specification for an AI task profile."""
    task_type: TaskType
    dev_model: str
    prod_model: str
    temperature: float = 0.1
    dev_temperature: float | None = None
    dev_thinking_level: str | None = None
    prod_thinking_level: str | None = None
    dev_thinking_budget: int | None = None
    prod_thinking_budget: int | None = None
    max_tokens: int | None = None
    preferred_node_id: str | None = None
    preferred_provider: str | None = None
    sanitize_input: bool = True
    use_boundary_tags: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedTaskConfig:
    """Concrete runtime configuration resolved for current execution environment."""
    profile: TaskProfile | None
    task_type: TaskType
    model: str
    temperature: float
    thinking_level: str | None
    thinking_budget: int | None
    max_tokens: int | None
    preferred_node_id: str | None
    preferred_provider: str | None
    sanitize_input: bool
    use_boundary_tags: bool


# Canonical task specifications registry
DEFAULT_TASK_SPECS: dict[TaskProfile, TaskSpec] = {
    # -------------------------------------------------------------------------
    # Portfolio Analysis & Multi-Stage DAG
    # -------------------------------------------------------------------------
    TaskProfile.PORTFOLIO_INSIGHTS: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-3.8-flash",
        prod_model="gemini-4-argon",
        temperature=0.15,
        dev_temperature=0.2,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        preferred_provider="gemini",
        sanitize_input=True,
    ),
    TaskProfile.PORTFOLIO_DAG_ALLOCATION: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.1,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.PORTFOLIO_DAG_QUALITY: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.1,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.PORTFOLIO_DAG_MACRO: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.1,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.PORTFOLIO_DAG_STRATEGY: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-3.8-flash",
        prod_model="gemini-4-argon",
        temperature=0.2,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.PORTFOLIO_DAG_SYNTHESIS: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-3.8-flash",
        prod_model="gemini-4-argon",
        temperature=0.15,
        dev_temperature=0.2,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),

    # -------------------------------------------------------------------------
    # Land Appraisal 3-Stage Consensus DAG
    # -------------------------------------------------------------------------
    TaskProfile.LAND_APPRAISAL_COMPS: TaskSpec(
        task_type=TaskType.RESEARCH,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-4-argon",
        temperature=0.1,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.LAND_APPRAISAL_AUDIT: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-4-argon",
        temperature=0.1,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.LAND_APPRAISAL_SYNTHESIS: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-4-argon",
        temperature=0.1,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),

    # -------------------------------------------------------------------------
    # Emails & Intelligence Briefs
    # -------------------------------------------------------------------------
    TaskProfile.WEEKLY_BRIEF: TaskSpec(
        task_type=TaskType.REASONING,
        dev_model="gemini-3.8-flash",
        prod_model="gemini-3.8-flash",
        temperature=0.2,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),
    TaskProfile.MONTHLY_EXPENSE_NOTE: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-3.8-flash",
        prod_model="gemini-3.8-flash",
        temperature=0.2,
        dev_thinking_level="LOW",
        prod_thinking_level="HIGH",
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
    ),

    # -------------------------------------------------------------------------
    # Expenses Operations
    # -------------------------------------------------------------------------
    TaskProfile.EXPENSE_CATEGORIZATION: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.1,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
        use_boundary_tags=True,
    ),
    TaskProfile.RECEIPT_PARSING: TaskSpec(
        task_type=TaskType.EXTRACTION,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.0,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
        use_boundary_tags=True,
    ),
    TaskProfile.STATEMENT_PARSING: TaskSpec(
        task_type=TaskType.EXTRACTION,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.0,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
        use_boundary_tags=True,
    ),
    TaskProfile.STATEMENT_MATCHING: TaskSpec(
        task_type=TaskType.EXTRACTION,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.0,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
        use_boundary_tags=True,
    ),
    TaskProfile.EXPENSE_ANOMALY: TaskSpec(
        task_type=TaskType.FAST,
        dev_model="gemini-2.5-flash-lite",
        prod_model="gemini-3.8-flash",
        temperature=0.1,
        dev_thinking_budget=0,
        prod_thinking_budget=0,
        preferred_node_id="gemini-cloud",
        sanitize_input=True,
        use_boundary_tags=True,
    ),
}


class AIConfigRegistry:
    """Manages task profiles, specifications, and dynamic environment resolution."""

    def __init__(self, specs: dict[TaskProfile, TaskSpec] | None = None):
        self._specs: dict[TaskProfile, TaskSpec] = dict(specs or DEFAULT_TASK_SPECS)

    def register(self, profile: TaskProfile, spec: TaskSpec) -> None:
        """Register or override a task specification."""
        self._specs[profile] = spec

    def get_spec(self, profile: TaskProfile | str) -> TaskSpec | None:
        """Retrieve the specification for a task profile."""
        if isinstance(profile, str):
            try:
                profile = TaskProfile(profile)
            except ValueError:
                return None
        return self._specs.get(profile)

    def resolve(
        self,
        task: TaskProfile | TaskType | str,
        is_debug: bool | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
    ) -> ResolvedTaskConfig:
        """Resolve concrete runtime configuration for a task in the current environment."""
        if is_debug is None:
            is_debug = getattr(settings, "DEBUG", True)

        profile: TaskProfile | None = None
        spec: TaskSpec | None = None

        if isinstance(task, TaskProfile):
            profile = task
            spec = self.get_spec(task)
        elif isinstance(task, str):
            try:
                profile = TaskProfile(task)
                spec = self.get_spec(profile)
            except ValueError:
                pass

        if spec is not None and profile is not None:
            # 1. Check for specific task environment variable override e.g. AI_TASK_MODEL_PORTFOLIO_INSIGHTS
            env_task_var = f"AI_TASK_MODEL_{profile.name}"
            env_task_model = os.environ.get(env_task_var)

            # 2. Check for domain-specific environment variable overrides
            domain_model = None
            if profile.name.startswith("EXPENSE") or profile.name in ("RECEIPT_PARSING", "STATEMENT_PARSING", "STATEMENT_MATCHING"):
                domain_model = (
                    getattr(settings, "EXPENSES_GEMINI_MODEL", "")
                    or os.environ.get("EXPENSES_GEMINI_MODEL", "")
                )
            elif profile.name.startswith("PORTFOLIO"):
                domain_model = (
                    getattr(settings, "GEMINI_MODEL", "")
                    or os.environ.get("GEMINI_MODEL", "")
                )

            # 3. Model precedence: direct override > task env var > (domain env var in prod) > spec
            if is_debug:
                resolved_model = (
                    model_override
                    or env_task_model
                    or spec.dev_model
                )
            else:
                resolved_model = (
                    model_override
                    or env_task_model
                    or domain_model
                    or spec.prod_model
                )

            # 4. Temperature precedence: override > dev_temp/prod_temp
            if temperature_override is not None:
                resolved_temp = temperature_override
            elif is_debug and spec.dev_temperature is not None:
                resolved_temp = spec.dev_temperature
            else:
                resolved_temp = spec.temperature

            thinking_level = spec.dev_thinking_level if is_debug else spec.prod_thinking_level
            thinking_budget = spec.dev_thinking_budget if is_debug else spec.prod_thinking_budget

            return ResolvedTaskConfig(
                profile=profile,
                task_type=spec.task_type,
                model=resolved_model,
                temperature=resolved_temp,
                thinking_level=thinking_level,
                thinking_budget=thinking_budget,
                max_tokens=spec.max_tokens,
                preferred_node_id=spec.preferred_node_id,
                preferred_provider=spec.preferred_provider,
                sanitize_input=spec.sanitize_input,
                use_boundary_tags=spec.use_boundary_tags,
            )

        # Fallback for generic TaskType or unknown string
        raw_task_type = task if isinstance(task, TaskType) else TaskType.GENERAL
        default_model = (
            getattr(settings, "GEMINI_MODEL", "")
            or os.environ.get("GEMINI_MODEL", "")
            or ("gemini-3.8-flash" if is_debug else "gemini-4-argon")
        )
        return ResolvedTaskConfig(
            profile=None,
            task_type=raw_task_type,
            model=model_override or default_model,
            temperature=temperature_override if temperature_override is not None else 0.2,
            thinking_level="LOW" if is_debug else "HIGH",
            thinking_budget=None,
            max_tokens=None,
            preferred_node_id=None,
            preferred_provider=None,
            sanitize_input=True,
            use_boundary_tags=False,
        )


# Global singleton instance
ai_config = AIConfigRegistry()
