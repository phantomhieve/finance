"""Business logic facade for the expense tracker: categories, ingestion, and analytics.

This module unifies:
- .categories: Default household categories, automated rules, and AI batch categorisation.
- .ingestion: Transaction creation, payment source resolution, and self-transfer settlement.
- .analytics: Monthly summaries, Indian FY metrics, trend curves, and pace tracking.
"""
from __future__ import annotations

from .analytics import (
    FIXED_CATEGORIES,
    INVESTMENT_CATEGORY,
    RISER_FLOOR,
    STACK_CATEGORIES,
    ZERO,
    _daily,
    _same_day_last_year,
    _spend,
    _sum,
    available_fys,
    fy_summary,
    live,
    month_bounds,
    month_summary,
    monthly_trend,
    shift_month,
    spend_q,
)
from .categories import (
    DEFAULT_CATEGORIES,
    _rule_for,
    ai_categorise_pending,
    categories_by_name,
    categorise_expense,
    ensure_default_categories,
    learn_category,
)
from .ingestion import (
    SETTLE_WINDOW_DAYS,
    _statement_paid_by,
    build_expense,
    manual_merchant,
    resolve_payment_source,
    settle_internal_movements,
)

__all__ = [
    # Analytics & Math constants
    "ZERO",
    "RISER_FLOOR",
    "FIXED_CATEGORIES",
    "INVESTMENT_CATEGORY",
    "STACK_CATEGORIES",
    "spend_q",
    "live",
    "month_bounds",
    "shift_month",
    "_sum",
    "_daily",
    "_spend",
    "_same_day_last_year",
    "month_summary",
    "monthly_trend",
    "fy_summary",
    "available_fys",
    # Categories & Learning
    "DEFAULT_CATEGORIES",
    "ensure_default_categories",
    "categories_by_name",
    "_rule_for",
    "categorise_expense",
    "ai_categorise_pending",
    "learn_category",
    # Ingestion & Transfers
    "SETTLE_WINDOW_DAYS",
    "_statement_paid_by",
    "settle_internal_movements",
    "resolve_payment_source",
    "build_expense",
    "manual_merchant",
]
