"""EMI schedule projection and tracking.

Bank/statement imports only create an EMI expense in the month the instalment is actually
debited. Once a loan's tenure is known (``emi_total_installments``) we can derive the rest of
the schedule from the latest real instalment: same monthly amount, same day-of-month, one
instalment per month until the tenure is reached. Nothing is stored — the schedule is derived
on every request, so a real debit arriving for a projected month automatically replaces its
projection and editing the tenure immediately re-plans the remaining months.
"""
import calendar
import datetime
from collections import defaultdict
from decimal import Decimal

from .models import Expense

ZERO = Decimal('0.00')
MAX_PROJECTION_MONTHS = 360


def _add_months(d: datetime.date, months: int) -> datetime.date:
    idx = d.year * 12 + (d.month - 1) + months
    year, month = divmod(idx, 12)
    month += 1
    return datetime.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _loans(group):
    """Group real (non-deleted) EMI instalment rows by loan reference."""
    rows = (
        Expense.objects.filter(group=group, is_emi=True, is_deleted=False, direction='DEBIT')
        .exclude(emi_reference='').exclude(emi_component='PURCHASE')
        .select_related('payment_source', 'category')
        .order_by('txn_date', 'id')
    )
    by_ref = defaultdict(list)
    for e in rows:
        by_ref[e.emi_reference].append(e)
    return by_ref


def emi_schedules(group, today=None):
    """Return one dict per active (or just-finished) EMI loan with its derived schedule."""
    today = today or datetime.date.today()
    schedules = []
    for ref, rows in _loans(group).items():
        total = max((e.emi_total_installments or 0 for e in rows), default=0)
        if not total:
            continue  # tenure unknown — nothing to project until the user sets it
        by_num = defaultdict(list)
        for e in rows:
            if e.emi_installment_num:
                by_num[e.emi_installment_num].append(e)
        if by_num:
            last_num = max(by_num)
            last_rows = by_num[last_num]
        else:
            # No instalment numbers parsed: fall back to counting distinct months with a debit.
            months = sorted({(e.txn_date.year, e.txn_date.month) for e in rows})
            last_num = len(months)
            last_rows = [e for e in rows if (e.txn_date.year, e.txn_date.month) == months[-1]]
        last_date = max(e.txn_date for e in last_rows)
        principal = sum((e.amount for e in last_rows if e.emi_component != 'INTEREST'), ZERO)
        interest = sum((e.amount for e in last_rows if e.emi_component == 'INTEREST'), ZERO)
        amount = principal + interest
        remaining = max(0, min(total - last_num, MAX_PROJECTION_MONTHS))

        upcoming = []
        for j in range(1, remaining + 1):
            upcoming.append({
                'num': last_num + j,
                'date': _add_months(last_date, j),
                'amount': amount,
                'principal': principal,
                'interest': interest,
            })
        paid_total = sum((e.amount for e in rows), ZERO)
        schedules.append({
            'ref': ref,
            'total_installments': total,
            'paid': min(last_num, total),
            'remaining': remaining,
            'progress_pct': round(min(last_num, total) / total * 100),
            'amount': amount,
            'principal': principal,
            'interest': interest,
            'paid_total': paid_total,
            'remaining_total': amount * remaining,
            'last_date': last_date,
            'next': upcoming[0] if upcoming else None,
            'ends_on': upcoming[-1]['date'] if upcoming else last_date,
            'upcoming': upcoming,
            'finished': remaining == 0,
            'payment_source': last_rows[0].payment_source,
            'item_id': last_rows[-1].pk,
            'last_num': last_num,
            'overdue': bool(upcoming and upcoming[0]['date'] < today.replace(day=1)),
        })
    schedules.sort(key=lambda s: (s['finished'], s['next']['date'] if s['next'] else datetime.date.max))
    return schedules


def emi_projection(group, start, end, today=None):
    """Projected (not yet debited) instalments falling inside [start, end], plus loan tracking.

    A projection is dropped when a real instalment for the same loan with an equal or higher
    number already exists in the window, so it never double-counts a posted debit.
    """
    today = today or datetime.date.today()
    schedules = emi_schedules(group, today=today)
    items = []
    for s in schedules:
        for u in s['upcoming']:
            if start <= u['date'] <= end:
                items.append({
                    **u,
                    'ref': s['ref'],
                    'total_installments': s['total_installments'],
                    'payment_source': s['payment_source'],
                    'item_id': s['item_id'],
                    'is_past': u['date'] < today,
                })
    items.sort(key=lambda i: (i['date'], i['ref']))
    return {
        'items': items,
        'total': sum((i['amount'] for i in items), ZERO),
        'loans': [s for s in schedules if not s['finished']],
        'finished_loans': [s for s in schedules if s['finished']],
        'monthly_commitment': sum((s['amount'] for s in schedules if not s['finished']), ZERO),
        'remaining_total': sum((s['remaining_total'] for s in schedules), ZERO),
    }

