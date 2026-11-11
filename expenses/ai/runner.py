"""Execution runner for expenses AI tasks using Vault AI Gateway."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from pftracker.ai_gateway import TaskProfile, TaskType, ai_config, gateway
from pftracker.concurrency import DjangoSafeThreadPoolExecutor

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
_WS_RE = re.compile(r"\s+")


def ai_available(task: TaskProfile | TaskType = TaskType.FAST) -> bool:
    """Check if AI is available for the given task tier via gateway or environment keys."""
    return (
        gateway.is_available(task)
        or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEYS"))
    )


def _generate(
    prompt: str,
    schema: type[T],
    system: str,
    task: TaskProfile | TaskType = TaskProfile.EXPENSE_CATEGORIZATION,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> T:
    """Execute structured generation with task-level tier routing and optional model override."""
    start_t = time.monotonic()
    preferred_node = "gemini-cloud" if gateway.node_registry.get("gemini-cloud") else None

    result = gateway.generate_structured(
        schema=schema,
        prompt=prompt,
        system=system,
        task=task,
        preferred_node_id=preferred_node,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    elapsed_ms = (time.monotonic() - start_t) * 1000.0
    task_name = task.value if hasattr(task, "value") else str(task)
    logger.debug(
        "Expenses AI completed structured call for task '%s' in %.1fms",
        task_name,
        elapsed_ms,
    )
    return result


def _canonical_categorise_key(item: dict[str, Any]) -> tuple[str, str, str]:
    """Build canonical (merchant_norm, direction, channel) key to deduplicate batch items."""
    raw_merchant = str(item.get("merchant") or item.get("raw") or "").strip().lower()
    merchant_norm = _WS_RE.sub(" ", raw_merchant)
    if not merchant_norm:
        return ("__id__", str(item.get("id")), "")
    direction = str(item.get("direction") or "DEBIT").strip().upper()
    channel = str(item.get("channel") or "").strip().upper()
    return (merchant_norm, direction, channel)


def categorise(
    items: list[dict[str, Any]],
    category_names: list[str],
    examples: list[tuple[str, str]],
) -> dict[int, tuple[str, float]]:
    """Batch-categorise transactions using canonical merchant deduplication and few-shot examples.

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
    allowed_ci = {c.strip().lower(): c for c in category_names if isinstance(c, str) and c.strip()}

    # Deduplicate identical (merchant_norm, direction, channel) rows before chunking
    representatives: list[dict[str, Any]] = []
    rep_id_to_member_ids: dict[int, list[int]] = {}
    key_to_rep_id: dict[tuple[str, str, str], int] = {}

    for item in items:
        item_id = int(item["id"])
        ckey = _canonical_categorise_key(item)
        if ckey in key_to_rep_id:
            rep_id_to_member_ids[key_to_rep_id[ckey]].append(item_id)
        else:
            key_to_rep_id[ckey] = item_id
            rep_id_to_member_ids[item_id] = [item_id]
            representatives.append(item)

    out: dict[int, tuple[str, float]] = {}

    for start in range(0, len(representatives), MAX_BATCH):
        chunk = representatives[start:start + MAX_BATCH]
        prompt = build_categorise_prompt(chunk, allowed, examples)
        try:
            parsed = _generate(
                prompt=prompt,
                schema=CategoryBatch,
                system=CATEGORISE_SYSTEM,
                task=TaskProfile.EXPENSE_CATEGORIZATION,
            )
        except Exception as exc:
            logger.warning("AI batch categorisation failed for %d items: %s", len(chunk), exc)
            continue

        for r in parsed.results:
            resolved_cat = r.category if r.category in allowed else allowed_ci.get((r.category or "").strip().lower())
            if resolved_cat:
                confidence = max(0.0, min(1.0, float(r.confidence)))
                for member_id in rep_id_to_member_ids.get(r.id, [r.id]):
                    out[member_id] = (resolved_cat, confidence)

    return out


def extract_transaction(subject: str, body: str) -> ExtractedTxn | None:
    """Extract structured transaction details from a single bank/card alert email."""
    if not ai_available(TaskProfile.RECEIPT_PARSING):
        return None

    text = build_extract_prompt(subject, body)
    try:
        result = _generate(
            prompt=text,
            schema=ExtractedTxn,
            system=EXTRACT_SYSTEM,
            task=TaskProfile.RECEIPT_PARSING,
        )
    except Exception as exc:
        logger.warning("AI transaction extraction failed: %s", exc)
        return None

    return result if result.is_transaction and result.amount else None


def _extract_single_statement_chunk(chunk: str) -> list[Any]:
    result = _generate(
        prompt=build_statement_prompt(chunk),
        schema=ExtractedLines,
        system=STATEMENT_SYSTEM,
        task=TaskProfile.STATEMENT_PARSING,
    )
    return list(result.lines)


def extract_statement_lines(text: str) -> list[Any]:
    """AI line-item extraction for statement PDFs the regex engine cannot (fully) parse.

    Long statements are split on line boundaries and processed concurrently (up to 3 workers)
    while strictly preserving original page/chunk order.
    """
    if not ai_available(TaskProfile.STATEMENT_PARSING) or not text:
        return []

    chunks = chunk_statement_text(text)
    if not chunks:
        return []

    if len(chunks) == 1:
        try:
            return _extract_single_statement_chunk(chunks[0])
        except Exception as exc:
            logger.warning("AI statement extraction failed: %s", exc)
            return []

    ordered_results: list[list[Any]] = [[] for _ in chunks]
    with DjangoSafeThreadPoolExecutor(max_workers=min(3, len(chunks))) as executor:
        futures = [
            (idx, executor.submit(_extract_single_statement_chunk, chunk))
            for idx, chunk in enumerate(chunks)
        ]
        for idx, fut in futures:
            try:
                ordered_results[idx] = fut.result()
            except Exception as exc:
                logger.warning("AI statement extraction failed on chunk %d/%d: %s", idx + 1, len(chunks), exc)

    out: list[Any] = []
    for lines in ordered_results:
        out.extend(lines)
    return out


def match_statement_lines(items: list[dict[str, Any]]) -> dict[int, LineMatch]:
    """Ask the model whether each statement line duplicates one of its candidate expenses.

    Args:
        items: [{'line_id', 'date', 'description', 'amount', 'direction',
                 'candidates': [{'expense_id', 'date', 'merchant', 'raw', 'amount', 'currency', ...}]}]

    Returns:
        {line_id: LineMatch}. Verdicts pointing at an expense outside that line's candidates are dropped.
    """
    if not items or not ai_available(TaskProfile.STATEMENT_MATCHING):
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
                task=TaskProfile.STATEMENT_MATCHING,
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


def monthly_commentary(
    summary_payload: dict[str, Any],
    model: str | None = None,
    thinking_level: str | None = None,
) -> dict[str, Any] | None:
    """Generate concise, grounded commentary for the monthly household digest email."""
    if not ai_available(TaskProfile.MONTHLY_EXPENSE_NOTE):
        return None

    cfg = ai_config.resolve(TaskProfile.MONTHLY_EXPENSE_NOTE)
    target_model = model or cfg.model
    target_thinking = thinking_level if thinking_level is not None else cfg.thinking_level

    prompt = build_monthly_note_prompt(summary_payload)
    try:
        note = _generate(
            prompt=prompt,
            schema=MonthlyNote,
            system=MONTHLY_NOTE_SYSTEM,
            task=TaskProfile.MONTHLY_EXPENSE_NOTE,
            model=target_model,
            thinking_level=target_thinking,
            temperature=cfg.temperature,
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
    if not items or not ai_available(TaskProfile.EXPENSE_ANOMALY):
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
                task=TaskProfile.EXPENSE_ANOMALY,
            )
            for anomaly in parsed.anomalies:
                if anomaly.is_suspicious and anomaly.reasons:
                    out[anomaly.id] = [r.strip() for r in anomaly.reasons if r.strip()]
        except Exception as exc:
            logger.warning("AI anomaly detection batch failed for %d items: %s", len(chunk), exc)
            continue

    return out
