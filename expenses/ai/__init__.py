"""Unified AI module for the Vault Expense Tracker.

Provides batch categorization, email/statement extraction fallback, and monthly commentary.
Maintains full backward compatibility with the legacy expenses.ai module.
"""
from __future__ import annotations

from .prompts import (
    ANOMALY_SYSTEM,
    CATEGORISE_SYSTEM,
    EXTRACT_SYSTEM,
    MONTHLY_NOTE_SYSTEM,
    STATEMENT_SYSTEM,
    build_anomaly_prompt,
    build_categorise_prompt,
    build_extract_prompt,
    build_monthly_note_prompt,
    build_statement_prompt,
)
from .runner import (
    MAX_BATCH,
    _generate,
    ai_available,
    categorise,
    detect_anomalies,
    extract_statement_lines,
    extract_transaction,
    monthly_commentary,
)
from .schemas import (
    AnomalyBatchResult,
    AnomalyItem,
    CategoryBatch,
    CategoryChoice,
    ExtractedLine,
    ExtractedLines,
    ExtractedTxn,
    MonthlyNote,
)

__all__ = [
    # Runner & Entry points
    "ai_available",
    "categorise",
    "detect_anomalies",
    "extract_transaction",
    "extract_statement_lines",
    "monthly_commentary",
    "_generate",
    "MAX_BATCH",
    # Schemas
    "CategoryChoice",
    "CategoryBatch",
    "ExtractedTxn",
    "ExtractedLine",
    "ExtractedLines",
    "MonthlyNote",
    "AnomalyItem",
    "AnomalyBatchResult",
    # Prompts
    "CATEGORISE_SYSTEM",
    "EXTRACT_SYSTEM",
    "STATEMENT_SYSTEM",
    "MONTHLY_NOTE_SYSTEM",
    "ANOMALY_SYSTEM",
    "build_categorise_prompt",
    "build_extract_prompt",
    "build_statement_prompt",
    "build_monthly_note_prompt",
    "build_anomaly_prompt",
]

