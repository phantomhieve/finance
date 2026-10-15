"""Suspicious transaction detection powered by Gemini AI with deterministic heuristic backstops."""
from __future__ import annotations

import datetime
import logging
import statistics
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable

from django.utils import timezone

from . import ai
from .models import Expense, ExpenseAuditRun

if TYPE_CHECKING:
    from tracker.models import AccountGroup, User

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 180
MIN_HISTORY = 5
LARGE_FLOOR = Decimal('2000')
NEW_MERCHANT_LARGE = Decimal('10000')
DUPLICATE_WINDOW_DAYS = 2
DUPLICATE_FLOOR = Decimal('500')
RAPID_WINDOW_MINUTES = 15
RAPID_COUNT = 3


def _history(expense: Expense):
    since = expense.txn_date - datetime.timedelta(days=LOOKBACK_DAYS)
    return (
        Expense.objects.filter(
            group=expense.group,
            is_deleted=False,
            direction='DEBIT',
            txn_date__gte=since,
            txn_date__lte=expense.txn_date,
        ).exclude(pk=expense.pk)
    )


def _large_for_category(expense: Expense, history) -> str | None:
    if expense.category_id is None or expense.amount < LARGE_FLOOR:
        return None
    amounts = [
        float(a)
        for a in history.filter(category_id=expense.category_id, currency=expense.currency).values_list(
            'amount', flat=True
        )
    ]
    if len(amounts) < MIN_HISTORY:
        return None
    median = statistics.median(amounts)
    mad = statistics.median(abs(a - median) for a in amounts) * 1.4826
    threshold = max(median * 3, median + 4 * mad)
    if float(expense.amount) > threshold:
        return (
            f'{float(expense.amount) / median:.0f}× your usual {expense.category.name} spend '
            f'(typical ₹{median:,.0f})'
        )
    return None


def _new_merchant_large(expense: Expense, history) -> str | None:
    if not expense.merchant_key or expense.amount < NEW_MERCHANT_LARGE:
        return None
    seen = (
        Expense.objects.filter(
            group=expense.group,
            merchant_key=expense.merchant_key,
            txn_date__lt=expense.txn_date,
        )
        .exclude(pk=expense.pk)
        .exists()
    )
    if not seen:
        return f'First-ever payment to {expense.merchant} and it is a large one'
    return None


def _duplicate(expense: Expense, history) -> str | None:
    if expense.source == 'STATEMENT' or expense.amount < DUPLICATE_FLOOR or not expense.merchant_key:
        return None
    window = datetime.timedelta(days=DUPLICATE_WINDOW_DAYS)
    dupes = (
        Expense.objects.filter(
            group=expense.group,
            is_deleted=False,
            amount=expense.amount,
            direction=expense.direction,
            merchant_key=expense.merchant_key,
            txn_date__gte=expense.txn_date - window,
            txn_date__lte=expense.txn_date + window,
        )
        .exclude(pk=expense.pk)
        .exclude(source='STATEMENT')
    )
    if expense.reference:
        dupes = dupes.exclude(reference=expense.reference)
    if dupes.exists():
        return 'Possible double charge — same amount at the same merchant within 2 days'
    return None


def _foreign(expense: Expense, history) -> str | None:
    if expense.currency != 'INR':
        return f'Foreign-currency charge ({expense.currency})'
    return None


def _odd_hour(expense: Expense, history) -> str | None:
    if expense.txn_time and expense.txn_time < datetime.time(5, 0) and expense.amount >= LARGE_FLOOR:
        return f'Made at {expense.txn_time:%H:%M}, an unusual hour'
    return None


def _rapid_fire(expense: Expense, history) -> str | None:
    if not (expense.txn_time and expense.payment_source_id):
        return None
    moment = datetime.datetime.combine(expense.txn_date, expense.txn_time)
    lo = (moment - datetime.timedelta(minutes=RAPID_WINDOW_MINUTES)).time()
    hi = (moment + datetime.timedelta(minutes=RAPID_WINDOW_MINUTES)).time()
    if lo > hi:  # window crosses midnight — skip rather than mis-count
        return None
    burst = history.filter(
        payment_source_id=expense.payment_source_id,
        txn_date=expense.txn_date,
        txn_time__gte=lo,
        txn_time__lte=hi,
    ).count()
    if burst + 1 >= RAPID_COUNT:
        return f'{burst + 1} charges on the same card within {RAPID_WINDOW_MINUTES} minutes'
    return None


RULES = [_large_for_category, _new_merchant_large, _duplicate, _foreign, _odd_hour, _rapid_fire]


def evaluate(expense: Expense) -> list[str]:
    """Deterministic rule-based evaluation (baseline statistical heuristics)."""
    if expense.direction != 'DEBIT' or expense.is_deleted or expense.category_source == 'MATCH':
        return []
    history = _history(expense)
    return [reason for rule in RULES if (reason := rule(expense, history))]


def _update_flags(expense: Expense, reasons: list[str], save: bool = True) -> None:
    """Internal helper to save flag state while respecting user reviews."""
    if expense.flag_reviewed and set(reasons) <= set(expense.flag_reasons or []):
        return
    expense.flag_reasons = reasons
    expense.is_flagged = bool(reasons)
    expense.flag_reviewed = False
    if save and expense.pk:
        expense.save(update_fields=['flag_reasons', 'is_flagged', 'flag_reviewed', 'updated_at'])


def ai_detect_anomalies_for_expenses(
    expenses: Iterable[Expense],
    group: AccountGroup | None = None,
) -> dict[int, list[str]]:
    """Evaluate a collection of expenses with Gemini AI forensic auditor.

    When AI is available, Gemini evaluates contextual anomalies across the batch.
    When AI is offline/unavailable, safely falls back to deterministic rule heuristics.
    """
    expense_list = [
        e for e in expenses
        if e.direction == 'DEBIT' and not e.is_deleted and e.category_source != 'MATCH'
    ]
    if not expense_list:
        return {}

    target_group = group or expense_list[0].group

    # When AI is offline, use deterministic heuristic rules
    if not ai.ai_available():
        results = {}
        for e in expense_list:
            reasons = evaluate(e)
            if reasons:
                results[e.pk] = reasons
                _update_flags(e, reasons)
        return results

    # Format items for AI analysis
    items: list[dict[str, Any]] = []
    for e in expense_list:
        rule_hints = evaluate(e)
        items.append({
            'id': e.pk,
            'amount': float(e.amount),
            'currency': e.currency,
            'merchant': e.merchant or e.merchant_raw or 'Unknown merchant',
            'raw': e.merchant_raw,
            'category': e.category.name if e.category else 'Uncategorised',
            'date': e.txn_date.isoformat(),
            'time': e.txn_time.isoformat() if e.txn_time else None,
            'channel': e.channel,
            'instrument': e.payment_source.kind if e.payment_source else 'OTHER',
            'rule_signals': rule_hints,
        })

    context = {
        'group': getattr(target_group, 'name', 'Household'),
        'audit_date': datetime.date.today().isoformat(),
    }

    try:
        ai_results = ai.detect_anomalies(items, context)
    except Exception as exc:
        logger.warning("AI anomaly detection call failed (%s); falling back to rule heuristics", exc)
        ai_results = {}

    final_flags: dict[int, list[str]] = {}
    for e in expense_list:
        reasons = list(ai_results.get(e.pk, []))
        if not reasons:
            # Fall back to high-confidence deterministic signals (duplicate charge or foreign currency)
            for r in evaluate(e):
                if 'double charge' in r or 'Foreign-currency' in r:
                    reasons.append(r)

        if reasons:
            final_flags[e.pk] = reasons
            _update_flags(e, reasons)
        elif e.is_flagged and not e.flag_reviewed:
            # Cleared by AI audit as healthy
            e.is_flagged = False
            e.flag_reasons = []
            if e.pk:
                e.save(update_fields=['is_flagged', 'flag_reasons', 'updated_at'])

    return final_flags


def apply_flags(expense: Expense, save: bool = True, use_ai: bool = False) -> list[str]:
    """Re-evaluate flags for an expense. A reviewed expense stays reviewed unless new reasons appear.

    Args:
        expense: Expense model instance to inspect.
        save: Whether to persist flags to database.
        use_ai: If True and AI is available, runs Gemini AI forensic audit; otherwise uses heuristics.
    """
    if use_ai and ai.ai_available():
        res = ai_detect_anomalies_for_expenses([expense])
        return res.get(expense.pk, [])

    reasons = evaluate(expense)
    _update_flags(expense, reasons, save=save)
    return reasons


AUDIT_COOLDOWN_DAYS = 7


def audit_cooldown_status(group: AccountGroup) -> dict[str, Any]:
    """Check whether an on-demand AI forensic audit is currently allowed for this household."""
    latest = ExpenseAuditRun.objects.filter(group=group).order_by('-created_at').first()
    if not latest:
        return {
            'can_audit': True,
            'latest_run': None,
            'remaining_days': 0,
            'remaining_hours': 0,
            'next_available': None,
        }

    cooldown = datetime.timedelta(days=AUDIT_COOLDOWN_DAYS)
    elapsed = timezone.now() - latest.created_at
    if elapsed >= cooldown:
        return {
            'can_audit': True,
            'latest_run': latest,
            'remaining_days': 0,
            'remaining_hours': 0,
            'next_available': None,
        }

    remaining = cooldown - elapsed
    rem_days = remaining.days
    rem_hours = int(remaining.seconds // 3600)
    next_available = latest.created_at + cooldown
    return {
        'can_audit': False,
        'latest_run': latest,
        'remaining_days': rem_days,
        'remaining_hours': rem_hours,
        'next_available': next_available,
    }


def ai_audit_expenses(
    group: AccountGroup,
    limit: int = 60,
    user: User | None = None,
) -> int:
    """Run an on-demand AI forensic audit of recent debit transactions for a household group.

    Records the audit execution in ExpenseAuditRun for auditing and weekly rate-limiting guardrails.
    Returns the count of flagged anomalous expenses.
    """
    recent = list(
        Expense.objects.filter(group=group, is_deleted=False, direction='DEBIT')
        .select_related('category', 'payment_source')
        .order_by('-txn_date')[:limit]
    )
    flagged_map = ai_detect_anomalies_for_expenses(recent, group=group)
    ExpenseAuditRun.objects.create(
        group=group,
        run_by=user if getattr(user, 'is_authenticated', False) else None,
        expenses_scanned=len(recent),
        anomalies_flagged=len(flagged_map),
        flagged_ids=list(flagged_map.keys()),
    )
    return len(flagged_map)

