"""Execution runner for expenses AI tasks using Vault AI Gateway."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from pftracker.ai_gateway import TaskType, gateway

from .prompts import (
    ANOMALY_SYSTEM,
    CATEGORISE_SYSTEM,
    EXTRACT_SYSTEM,
    MATCH_SYSTEM,
    MONTHLY_NOTE_SYSTEM,
    STATEMENT_SYSTEM,
    build_anomaly_prompt,
    build_categorise_prompt,
    build_extract_prompt,
    build_match_prompt,
    build_monthly_note_prompt,
    build_statement_prompt,
    chunk_statement_text,
)
from .schemas import (
    AnomalyBatchResult,
    CategoryBatch,
    ExtractedLines,
    ExtractedTxn,
    LineMatch,
    LineMatchBatch,
    MonthlyNote,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
MAX_BATCH = 40
MATCH_BATCH = 20


def ai_available(task: TaskType = TaskType.FAST) -> bool:
    """Check if AI is available for the given task tier via gateway or environment keys."""
    return (
        gateway.is_available(task)
        or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEYS"))
    )


def _generate(
    prompt: str,
    schema: type[T],
    system: str,
    task: TaskType = TaskType.FAST,
    temperature: float = 0.1,
    max_tokens: int | None = None,
) -> T:
    """Execute structured generation with task-level tier routing and model override."""
    model_override = os.environ.get("EXPENSES_GEMINI_MODEL")
    start_t = time.monotonic()
    preferred_node = "gemini-cloud" if gateway.node_registry.get("gemini-cloud") else None

    result = gateway.generate_structured(
        schema=schema,
        prompt=prompt,
        system=system,
        task=task,
        preferred_node_id=preferred_node,
        model=model_override,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    elapsed_ms = (time.monotonic() - start_t) * 1000.0
    logger.debug(
        "Expenses AI completed structured call for task '%s' in %.1fms",
        task.value,
        elapsed_ms,
    )
    return result


def categorise(
    items: list[dict[str, Any]],
    category_names: list[str],
    examples: list[tuple[str, str]],
) -> dict[int, tuple[str, float]]:
    """Batch-categorise transactions using past decisions as few-shot examples.

    Args:
        items: List of transaction dicts [{'id', 'merchant', 'raw', 'amount', 'direction', 'channel'}].
        category_names: Allowed category names in the household.
        examples: [(merchant_label, category_name)] learned from user edits.

    Returns:
        Mapping of {item_id: (category_name, confidence)} for valid predictions.
    """
    if not items or not ai_available(TaskType.FAST):
        return {}

    allowed = set(category_names)
    out: dict[int, tuple[str, float]] = {}

    for start in range(0, len(items), MAX_BATCH):
        chunk = items[start:start + MAX_BATCH]
        prompt = build_categorise_prompt(chunk, allowed, examples)
        try:
            parsed = _generate(
                prompt=prompt,
                schema=CategoryBatch,
                system=CATEGORISE_SYSTEM,
                task=TaskType.FAST,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("AI batch categorisation failed for %d items: %s", len(chunk), exc)
            continue

        for r in parsed.results:
            if r.category in allowed:
                confidence = max(0.0, min(1.0, float(r.confidence)))
                out[r.id] = (r.category, confidence)

    return out


def extract_transaction(subject: str, body: str) -> ExtractedTxn | None:
    """Extract structured transaction details from a single bank/card alert email."""
    if not ai_available(TaskType.EXTRACTION):
        return None

    text = build_extract_prompt(subject, body)
    try:
        result = _generate(
            prompt=text,
            schema=ExtractedTxn,
            system=EXTRACT_SYSTEM,
            task=TaskType.EXTRACTION,
            temperature=0.0,  # Zero temperature for deterministic extraction
        )
    except Exception as exc:
        logger.warning("AI transaction extraction failed: %s", exc)
        return None

    return result if result.is_transaction and result.amount else None


def extract_statement_lines(text: str) -> list[Any]:
    """AI line-item extraction for statement PDFs the regex engine cannot (fully) parse.

    Long statements are processed in line-aligned chunks so later pages are not dropped.
    """
    if not ai_available(TaskType.EXTRACTION) or not text:
        return []

    out: list[Any] = []
    for chunk in chunk_statement_text(text):
        try:
            result = _generate(
                prompt=build_statement_prompt(chunk),
                schema=ExtractedLines,
                system=STATEMENT_SYSTEM,
                task=TaskType.EXTRACTION,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("AI statement extraction failed: %s", exc)
            continue
        out.extend(result.lines)
    return out


def match_statement_lines(items: list[dict[str, Any]]) -> dict[int, LineMatch]:
    """Ask the model whether each statement line duplicates one of its candidate expenses.

    Args:
        items: [{'line_id', 'date', 'description', 'amount', 'direction',
                 'candidates': [{'expense_id', 'date', 'merchant', 'raw', 'amount', 'currency', ...}]}]

    Returns:
        {line_id: LineMatch}. Verdicts pointing at an expense outside that line's candidates are dropped.
    """
    if not items or not ai_available(TaskType.EXTRACTION):
        return {}

    allowed = {it["line_id"]: {c["expense_id"] for c in it["candidates"]} for it in items}
    out: dict[int, LineMatch] = {}
    for start in range(0, len(items), MATCH_BATCH):
        chunk = items[start:start + MATCH_BATCH]
        try:
            parsed = _generate(
                prompt=build_match_prompt(chunk),
                schema=LineMatchBatch,
                system=MATCH_SYSTEM,
                task=TaskType.EXTRACTION,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("AI statement matching failed for %d lines: %s", len(chunk), exc)
            continue
        for verdict in parsed.matches:
            if verdict.line_id not in allowed:
                continue
            if verdict.expense_id is not None and verdict.expense_id not in allowed[verdict.line_id]:
                continue
            verdict.confidence = max(0.0, min(1.0, float(verdict.confidence)))
            out[verdict.line_id] = verdict
    return out


def monthly_commentary(summary_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Generate concise, grounded commentary for the monthly household digest email."""
    if not ai_available(TaskType.FAST):
        return None

    prompt = build_monthly_note_prompt(summary_payload)
    try:
        note = _generate(
            prompt=prompt,
            schema=MonthlyNote,
            system=MONTHLY_NOTE_SYSTEM,
            task=TaskType.FAST,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("AI monthly commentary generation failed: %s", exc)
        return None

    return note.model_dump()


def detect_anomalies(
    items: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[int, list[str]]:
    """Audit transactions using Gemini AI to detect suspicious anomalies.

    Args:
        items: List of transaction dicts [{'id', 'merchant', 'amount', 'category', 'date', 'time', 'instrument', ...}].
        context: Household context like typical monthly spend, categories, etc.

    Returns:
        Mapping of {expense_id: [reason1, reason2]} for transactions flagged as suspicious.
    """
    if not items or not ai_available(TaskType.FAST):
        return {}

    context = context or {}
    out: dict[int, list[str]] = {}

    for start in range(0, len(items), 30):
        chunk = items[start:start + 30]
        prompt = build_anomaly_prompt(chunk, context)
        try:
            parsed = _generate(
                prompt=prompt,
                schema=AnomalyBatchResult,
                system=ANOMALY_SYSTEM,
                task=TaskType.FAST,
                temperature=0.1,
            )
            for anomaly in parsed.anomalies:
                if anomaly.is_suspicious and anomaly.reasons:
                    out[anomaly.id] = [r.strip() for r in anomaly.reasons if r.strip()]
        except Exception as exc:
            logger.warning("AI anomaly detection batch failed for %d items: %s", len(chunk), exc)
            continue

    return out

