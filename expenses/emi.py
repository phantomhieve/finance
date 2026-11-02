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


def emi_projection(group, start, end, today=None, ongoing=None):
    """Projected (not yet debited) instalments falling inside [start, end], plus unified loan cards.

    A projection is dropped when a real instalment for the same loan with an equal or higher
    number already exists in the window, so it never double-counts a posted debit.
    """
    today = today or datetime.date.today()
    schedules = emi_schedules(group, today=today)
    items = []
    projected_by_ref = {}
    for s in schedules:
        for u in s['upcoming']:
            if start <= u['date'] <= end:
                it = {
                    **u,
                    'ref': s['ref'],
                    'total_installments': s['total_installments'],
                    'payment_source': s['payment_source'],
                    'item_id': s['item_id'],
                    'is_past': u['date'] < today,
                }
                items.append(it)
                projected_by_ref[s['ref']] = it
    items.sort(key=lambda i: (i['date'], i['ref']))

    if ongoing is None:
        month_debits = (
            Expense.objects.filter(
                group=group, is_emi=True, is_deleted=False, direction='DEBIT',
                txn_date__gte=start, txn_date__lte=end
            )
            .exclude(emi_reference='').exclude(emi_component='PURCHASE')
            .select_related('payment_source')
        )
        ongoing_by_loan = defaultdict(lambda: {
            'ref': '', 'num': None, 'total_installments': None,
            'principal': ZERO, 'interest': ZERO, 'total': ZERO,
            'payment_source': None, 'item_id': None, 'items': []
        })
        for e in month_debits:
            rec = ongoing_by_loan[e.emi_reference]
            rec['ref'] = e.emi_reference
            if e.emi_installment_num and not rec['num']:
                rec['num'] = e.emi_installment_num
            if e.emi_total_installments and not rec['total_installments']:
                rec['total_installments'] = e.emi_total_installments
            if not rec['item_id']:
                rec['item_id'] = e.pk
            rec['payment_source'] = e.payment_source
            if e.emi_component == 'INTEREST':
                rec['interest'] += e.amount
            else:
                rec['principal'] += e.amount
            rec['total'] += e.amount
            rec['items'].append(e)
        ongoing_list = list(ongoing_by_loan.values())
    else:
        ongoing_list = ongoing

    ongoing_by_ref = {}
    for rec in ongoing_list:
        ref = rec.get('ref')
        if ref:
            ongoing_by_ref[ref] = rec

    active_schedules = [s for s in schedules if not s['finished']]
    schedule_by_ref = {s['ref']: s for s in schedules}

    # Collect relevant loans for this month:
    # 1. Debited this month
    # 2. Projected to be debited this month
    # 3. Any other active loans (not finished)
    loan_refs = []
    seen = set()
    for ref in ongoing_by_ref:
        if ref not in seen:
            seen.add(ref)
            loan_refs.append(ref)
    for it in items:
        if it['ref'] not in seen:
            seen.add(it['ref'])
            loan_refs.append(it['ref'])
    for s in active_schedules:
        if s['ref'] not in seen:
            seen.add(s['ref'])
            loan_refs.append(s['ref'])

    cards = []
    for ref in loan_refs:
        on = ongoing_by_ref.get(ref)
        proj = projected_by_ref.get(ref)
        sched = schedule_by_ref.get(ref)

        total_installments = (
            (on.get('total_installments') if on else None)
            or (sched.get('total_installments') if sched else None)
            or (proj.get('total_installments') if proj else None)
        )
        payment_source = (
            (on.get('payment_source') if on else None)
            or (sched.get('payment_source') if sched else None)
            or (proj.get('payment_source') if proj else None)
        )
        item_id = (
            (on.get('item_id') if on else None)
            or (sched.get('item_id') if sched else None)
            or (proj.get('item_id') if proj else None)
        )

        if on:
            is_paid = True
            is_due = False
            is_past = False
            on_items = on.get('items') or []
            status_date = max((e.txn_date for e in on_items), default=None)
            num = on.get('num')
            amount = on.get('total', ZERO)
            principal = on.get('principal', ZERO)
            interest = on.get('interest', ZERO)
        elif proj:
            is_paid = False
            is_due = True
            is_past = proj.get('is_past', False)
            status_date = proj.get('date')
            num = proj.get('num')
            amount = proj.get('amount', ZERO)
            principal = proj.get('principal', ZERO)
            interest = proj.get('interest', ZERO)
        else:
            is_paid = False
            is_due = False
            is_past = False
            status_date = sched['next']['date'] if sched and sched.get('next') else None
            num = None
            amount = sched.get('amount', ZERO) if sched else ZERO
            principal = sched.get('principal', ZERO) if sched else ZERO
            interest = sched.get('interest', ZERO) if sched else ZERO

        monthly_amount = sched['amount'] if sched else amount
        tenure_unknown = not bool(total_installments)
        is_final = bool(total_installments and num and num >= total_installments)

        if sched:
            paid_installments = sched['paid']
            remaining_installments = sched['remaining']
            progress_pct = sched['progress_pct']
            remaining_total = sched['remaining_total']
            ends_on = sched['ends_on']
            last_num = sched['last_num']
        elif on and total_installments and num:
            paid_installments = num
            remaining_installments = max(0, total_installments - num)
            progress_pct = round(num / total_installments * 100)
            remaining_total = monthly_amount * remaining_installments
            ends_on = _add_months(status_date, remaining_installments) if status_date else None
            last_num = num
        else:
            paid_installments = (on.get('num') if on else None) or 0
            remaining_installments = None
            progress_pct = 0
            remaining_total = None
            ends_on = None
            last_num = on.get('num') if on else None

        cards.append({
            'ref': ref,
            'payment_source': payment_source,
            'item_id': item_id,
            'amount': amount,
            'monthly_amount': monthly_amount,
            'principal': principal,
            'interest': interest,
            'is_paid': is_paid,
            'is_due': is_due,
            'is_past': is_past,
            'status_date': status_date,
            'num': num,
            'total_installments': total_installments,
            'tenure_unknown': tenure_unknown,
            'is_final': is_final,
            'paid_installments': paid_installments,
            'remaining_installments': remaining_installments,
            'progress_pct': progress_pct,
            'remaining_total': remaining_total,
            'ends_on': ends_on,
            'last_num': last_num,
            'current_or_last_num': num or last_num or '',
        })

    this_month_expected = sum((c['amount'] for c in cards if c['is_due']), ZERO)
    this_month_paid = sum((c['amount'] for c in cards if c['is_paid']), ZERO)
    active_monthly_commitment = sum((s['amount'] for s in schedules if not s['finished']), ZERO)
    effective_monthly_commitment = active_monthly_commitment or sum((c['monthly_amount'] for c in cards), ZERO)

    return {
        'items': items,
        'total': sum((i['amount'] for i in items), ZERO),
        'loans': active_schedules,
        'finished_loans': [s for s in schedules if s['finished']],
        'monthly_commitment': active_monthly_commitment,
        'effective_monthly_commitment': effective_monthly_commitment,
        'remaining_total': sum((s['remaining_total'] for s in schedules), ZERO),
        'cards': cards,
        'this_month_expected': this_month_expected,
        'this_month_paid': this_month_paid,
    }

