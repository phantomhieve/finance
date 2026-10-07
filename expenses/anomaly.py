"""Rule-based suspicious-transaction detection.

Each rule returns a short human reason; an expense is flagged when any rule fires.
Robust statistics (median / MAD) keep one big purchase from masking the next.
"""
import datetime
import statistics
from decimal import Decimal

from .models import Expense

LOOKBACK_DAYS = 180
MIN_HISTORY = 5
LARGE_FLOOR = Decimal('2000')
NEW_MERCHANT_LARGE = Decimal('10000')
DUPLICATE_WINDOW_DAYS = 2
DUPLICATE_FLOOR = Decimal('500')
RAPID_WINDOW_MINUTES = 15
RAPID_COUNT = 3


def _history(expense):
    since = expense.txn_date - datetime.timedelta(days=LOOKBACK_DAYS)
    return (Expense.objects.filter(group=expense.group, is_deleted=False, direction='DEBIT',
                                   txn_date__gte=since, txn_date__lte=expense.txn_date)
            .exclude(pk=expense.pk))


def _large_for_category(expense, history):
    if expense.category_id is None or expense.amount < LARGE_FLOOR:
        return None
    amounts = [float(a) for a in history.filter(category_id=expense.category_id, currency=expense.currency)
               .values_list('amount', flat=True)]
    if len(amounts) < MIN_HISTORY:
        return None
    median = statistics.median(amounts)
    mad = statistics.median(abs(a - median) for a in amounts) * 1.4826
    threshold = max(median * 3, median + 4 * mad)
    if float(expense.amount) > threshold:
        return (f'{float(expense.amount) / median:.0f}× your usual {expense.category.name} spend '
                f'(typical ₹{median:,.0f})')
    return None


def _new_merchant_large(expense, history):
    if not expense.merchant_key or expense.amount < NEW_MERCHANT_LARGE:
        return None
    seen = Expense.objects.filter(group=expense.group, merchant_key=expense.merchant_key,
                                  txn_date__lt=expense.txn_date).exclude(pk=expense.pk).exists()
    if not seen:
        return f'First-ever payment to {expense.merchant} and it is a large one'
    return None


def _duplicate(expense, history):
    if expense.source == 'STATEMENT' or expense.amount < DUPLICATE_FLOOR or not expense.merchant_key:
        return None
    window = datetime.timedelta(days=DUPLICATE_WINDOW_DAYS)
    dupes = Expense.objects.filter(
        group=expense.group, is_deleted=False, amount=expense.amount, direction=expense.direction,
        merchant_key=expense.merchant_key,
        txn_date__gte=expense.txn_date - window, txn_date__lte=expense.txn_date + window,
    ).exclude(pk=expense.pk).exclude(source='STATEMENT')
    if expense.reference:
        dupes = dupes.exclude(reference=expense.reference)
    if dupes.exists():
        return 'Possible double charge — same amount at the same merchant within 2 days'
    return None


def _foreign(expense, history):
    if expense.currency != 'INR':
        return f'Foreign-currency charge ({expense.currency})'
    return None


def _odd_hour(expense, history):
    if expense.txn_time and expense.txn_time < datetime.time(5, 0) and expense.amount >= LARGE_FLOOR:
        return f'Made at {expense.txn_time:%H:%M}, an unusual hour'
    return None


def _rapid_fire(expense, history):
    if not (expense.txn_time and expense.payment_source_id):
        return None
    moment = datetime.datetime.combine(expense.txn_date, expense.txn_time)
    lo = (moment - datetime.timedelta(minutes=RAPID_WINDOW_MINUTES)).time()
    hi = (moment + datetime.timedelta(minutes=RAPID_WINDOW_MINUTES)).time()
    if lo > hi:  # window crosses midnight — skip rather than mis-count
        return None
    burst = history.filter(payment_source_id=expense.payment_source_id, txn_date=expense.txn_date,
                           txn_time__gte=lo, txn_time__lte=hi).count()
    if burst + 1 >= RAPID_COUNT:
        return f'{burst + 1} charges on the same card within {RAPID_WINDOW_MINUTES} minutes'
    return None


RULES = [_large_for_category, _new_merchant_large, _duplicate, _foreign, _odd_hour, _rapid_fire]


def evaluate(expense):
    if expense.direction != 'DEBIT' or expense.is_deleted or expense.category_source == 'MATCH':
        return []
    history = _history(expense)
    return [reason for rule in RULES if (reason := rule(expense, history))]


def apply_flags(expense, save=True):
    """Re-evaluate flags. A reviewed expense stays reviewed unless new reasons appear."""
    reasons = evaluate(expense)
    if expense.flag_reviewed and set(reasons) <= set(expense.flag_reasons or []):
        return reasons
    expense.flag_reasons = reasons
    expense.is_flagged = bool(reasons)
    expense.flag_reviewed = False
    if save:
        expense.save(update_fields=['flag_reasons', 'is_flagged', 'flag_reviewed', 'updated_at'])
    return reasons
