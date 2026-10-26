"""Financial calculation standards and analytics for expenses (monthly summaries, FY trends, pacing)."""
from __future__ import annotations

import calendar
import datetime
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import Case, Count, F, Q, QuerySet, Sum, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from pftracker.utils import fy_label
from .models import Expense, PaymentSource

if TYPE_CHECKING:
    from tracker.models import AccountGroup

ZERO = Decimal('0')
RISER_FLOOR = Decimal('500')
# Fixed monthly costs are left out of "day-to-day" figures so rent doesn't drown everything else.
FIXED_CATEGORIES = ('Rent & Housing', 'EMI & Loans', 'Insurance')
# Investment debits reveal the portfolio, so they are only shown to people who can see it.
INVESTMENT_CATEGORY = 'Investments'
STACK_CATEGORIES = 5


def spend_q() -> Q:
    """Debits that count as spending (uncategorised debits count until filed elsewhere)."""
    return Q(direction='DEBIT') & (Q(category__isnull=True) | Q(category__kind='SPEND'))


def credit_refunds_q() -> Q:
    """Filter Q for incoming CREDIT transactions that qualify as refunds (excludes transfers and card bill payments)."""
    return (
        Q(direction='CREDIT')
        & ~Q(category__kind='TRANSFER')
        & ~Q(category__name__in=('Credit Card Payment', 'Transfers'))
        & ~Q(payment_source__kind='CREDIT_CARD', merchant__in=('Credit Card Bill Payment', 'Unknown merchant', 'Unknown'))
    )


def all_refunds_q() -> Q:
    """Filter Q matching either debit expenses that have been refunded or incoming credit refunds."""
    return (
        Q(refunded_amount__gt=ZERO)
        | Q(refund_date__isnull=False)
        | credit_refunds_q()
    )


def live(group: AccountGroup) -> QuerySet[Expense]:
    """Active non-deleted expenses for the household group (excluding absorbed refunds)."""
    return Expense.objects.filter(group=group, is_deleted=False, refund_of__isnull=True)


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    """Return (first_day, last_day) of a month."""
    return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add delta months to (year, month). Returns (new_year, new_month)."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _sum(qs: QuerySet[Expense]) -> Decimal:
    """Net spend accounting for refunds: sum(amount - min(amount, refunded_amount))."""
    res = qs.aggregate(
        t=Sum(
            Case(
                When(refunded_amount__gte=F('amount'), then=ZERO),
                When(refunded_amount__gt=ZERO, then=F('amount') - F('refunded_amount')),
                default=F('amount'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['t']
    return res or ZERO


def _daily(qs: QuerySet[Expense], days: int) -> list[Decimal]:
    by_day = defaultdict(lambda: ZERO)
    for d, amt, ref in qs.values_list('txn_date', 'amount', 'refunded_amount'):
        if ref and ref >= amt:
            continue
        net = amt - (ref or ZERO)
        by_day[d.day] += net
    return [by_day.get(d, ZERO) for d in range(1, days + 1)]


def _spend(group: AccountGroup, start: datetime.date, end: datetime.date, mail_only: bool) -> QuerySet[Expense]:
    qs = live(group).filter(txn_date__gte=start, txn_date__lte=end, currency='INR').filter(spend_q())
    return qs.exclude(source='MANUAL') if mail_only else qs


def _same_day_last_year(d: datetime.date) -> datetime.date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def month_summary(
    group: AccountGroup,
    year: int,
    month: int,
    mail_only: bool = False,
    today: datetime.date | None = None,
    hide_investments: bool = False,
) -> dict[str, Any]:
    """Calculate comprehensive monthly metrics, pace against previous month, and category breakdown."""
    today = today or timezone.localdate()
    start, end = month_bounds(year, month)
    month_all = live(group).filter(txn_date__gte=start, txn_date__lte=end)
    if mail_only:
        month_all = month_all.exclude(source='MANUAL')
    if hide_investments:
        month_all = month_all.exclude(category__name=INVESTMENT_CATEGORY)

    qs = month_all.filter(currency='INR')
    spend_qs = qs.filter(spend_q())
    total = _sum(spend_qs)
    days = calendar.monthrange(year, month)[1]
    daily = _daily(spend_qs, days)

    py, pm = shift_month(year, month, -1)
    p_start, p_end = month_bounds(py, pm)
    prev_qs = _spend(group, p_start, p_end, mail_only)
    prev_total = _sum(prev_qs)
    prev_daily = _daily(prev_qs, (p_end - p_start).days + 1)

    # A month in progress is compared with last month up to the same day, not its full total.
    pace = None
    compare_qs = prev_qs
    if start <= today <= end:
        elapsed = today.day
        compare_qs = prev_qs.filter(txn_date__day__lte=elapsed)
        prev_to_date = sum(prev_daily[:elapsed], ZERO)
        pace = {
            'day': elapsed,
            'days': days,
            'prev_to_date': prev_to_date,
            'delta': total - prev_to_date,
            'gap': abs(total - prev_to_date),
            'delta_pct': round((total - prev_to_date) / prev_to_date * 100) if prev_to_date else None,
            'projected': total + max(ZERO, prev_total - prev_to_date) if prev_total else None,
        }
    prev_by_cat = dict(compare_qs.values_list('category__name').annotate(t=Sum('amount')))

    categories = []
    for row in (spend_qs.values('category__id', 'category__name', 'category__icon', 'category__hue')
                .annotate(total=Sum('amount'), count=Count('id')).order_by('-total')):
        name = row['category__name'] or 'Uncategorised'
        prev = prev_by_cat.get(row['category__name']) or ZERO
        categories.append({
            'id': row['category__id'],
            'name': name,
            'icon': row['category__icon'] or 'help',
            'hue': row['category__hue'] if row['category__hue'] is not None else 230,
            'total': row['total'],
            'count': row['count'],
            'pct': round(row['total'] / total * 100) if total else 0,
            'prev': prev,
            'delta': row['total'] - prev,
            'gap': abs(row['total'] - prev),
        })

    members = []
    for row in (spend_qs.values('member__id', 'member__first_name', 'member__username')
                .annotate(total=Sum('amount'), count=Count('id')).order_by('-total')):
        members.append({
            'id': row['member__id'],
            'name': row['member__first_name'] or row['member__username'] or 'Shared / unassigned',
            'total': row['total'],
            'count': row['count'],
            'pct': round(row['total'] / total * 100) if total else 0,
        })

    sources = []
    source_rows = list(spend_qs.values('payment_source__id').annotate(total=Sum('amount'), count=Count('id'))
                       .order_by('-total'))
    source_map = PaymentSource.objects.in_bulk([r['payment_source__id'] for r in source_rows if r['payment_source__id']])
    for row in source_rows:
        ps = source_map.get(row['payment_source__id'])
        sources.append({
            'name': ps.display_name if ps else 'Unknown / manual',
            'icon': ps.icon if ps else 'wallet',
            'total': row['total'],
            'count': row['count'],
        })

    merchants = list(
        spend_qs.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')[:8]
    )
    risers = [c for c in categories if c['delta'] >= RISER_FLOOR]
    flexible = spend_qs.exclude(category__name__in=FIXED_CATEGORIES)
    frequent = (flexible.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
                .filter(count__gte=2).order_by('-count', '-total').first())

    agg = spend_qs.aggregate(
        gross=Sum('amount'),
        debit_refunds=Sum(
            Case(
                When(refunded_amount__gt=ZERO, then=F('refunded_amount')),
                default=ZERO,
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        ),
    )
    gross_total = agg['gross'] or ZERO
    debit_refunds = agg['debit_refunds'] or ZERO
    credit_refunds = (
        month_all.filter(refund_of__isnull=True)
        .filter(credit_refunds_q())
        .aggregate(t=Sum('amount'))['t'] or ZERO
    )
    refunded_total = debit_refunds + credit_refunds
    total = max(ZERO, total - credit_refunds)
    refund_count = month_all.filter(all_refunds_q()).count()

    # Credit card EMI metrics
    emi_qs = month_all.filter(is_emi=True)
    ongoing_by_loan = defaultdict(lambda: {
        'ref': '', 'num': None, 'total_installments': None, 'pending_installments': None,
        'principal': ZERO, 'interest': ZERO, 'total': ZERO, 'payment_source': None,
        'item_id': None, 'items': []
    })
    for e in emi_qs.exclude(emi_component='PURCHASE'):
        key = (e.emi_reference, e.emi_installment_num)
        rec = ongoing_by_loan[key]
        rec['ref'] = e.emi_reference
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

    known_tenures = dict(
        Expense.objects.filter(group=group, is_emi=True, emi_total_installments__isnull=False)
        .exclude(emi_reference='')
        .order_by('updated_at')
        .values_list('emi_reference', 'emi_total_installments')
    )
    for rec in ongoing_by_loan.values():
        if not rec['total_installments'] and rec['ref'] in known_tenures:
            rec['total_installments'] = known_tenures[rec['ref']]
        if rec['total_installments'] and rec['num'] is not None:
            rec['pending_installments'] = max(0, rec['total_installments'] - rec['num'])

    ongoing_emis = sorted(ongoing_by_loan.values(), key=lambda x: -x['total'])
    emi_installments_total = sum((x['total'] for x in ongoing_emis), ZERO)

    converted_purchases = list(emi_qs.filter(emi_component='PURCHASE').select_related('payment_source').order_by('-amount'))
    converted_total = sum((e.amount for e in converted_purchases), ZERO)

    emi_summary = {
        'count': emi_qs.count(),
        'ongoing': ongoing_emis,
        'ongoing_total': emi_installments_total,
        'converted': converted_purchases,
        'converted_total': converted_total,
        'monthly_commitment': emi_installments_total,
    }

    return {
        'year': year,
        'month': month,
        'start': start,
        'end': end,
        'label': start.strftime('%B %Y'),
        'prev_label': p_start.strftime('%B'),
        'total': total,
        'gross_total': gross_total,
        'refunded_total': refunded_total,
        'refund_count': refund_count,
        'emi_summary': emi_summary,
        'emi_count': emi_qs.count(),
        'prev_total': prev_total,
        'delta': total - prev_total,
        'delta_pct': round((total - prev_total) / prev_total * 100) if prev_total else None,
        'pace': pace,
        'per_day': _sum(flexible) / (pace['day'] if pace else days),
        'biggest': flexible.select_related('category').order_by('-amount').first(),
        'frequent': frequent,
        'riser': max(risers, key=lambda c: c['delta']) if risers else None,
        'prev_daily': [float(v) for v in prev_daily],
        'income': _sum(qs.filter(direction='CREDIT', category__kind='INCOME')),
        'transfers': _sum(qs.filter(direction='DEBIT', category__kind='TRANSFER')),
        'count': spend_qs.count(),
        'categories': categories,
        'members': members,
        'sources': sources,
        'merchants': merchants,
        'daily': [float(v) for v in daily],
        'flagged': list(month_all.filter(is_flagged=True).select_related('category', 'payment_source', 'member')
                        .order_by('-txn_date')),
        'uncategorised': qs.filter(direction='DEBIT', category__isnull=True).count(),
        'from_statements': qs.filter(source='STATEMENT').count(),
        'foreign': list(month_all.exclude(currency='INR')
                        .values('currency').annotate(total=Sum('amount'), count=Count('id'))),
    }


def monthly_trend(
    group: AccountGroup,
    year: int,
    month: int,
    n: int = 6,
    mail_only: bool = False,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """Spend for the n months ending at (year, month), oldest first."""
    today = today or timezone.localdate()
    sy, sm = shift_month(year, month, -(n - 1))
    _, end = month_bounds(year, month)
    totals = {
        (row['mo'].year, row['mo'].month): row['t']
        for row in _spend(group, datetime.date(sy, sm, 1), end, mail_only)
        .annotate(mo=TruncMonth('txn_date')).values('mo').annotate(t=Sum('amount'))
    }
    out = []
    for i in range(n):
        y, m = shift_month(sy, sm, i)
        out.append({
            'year': y,
            'month': m,
            'param': f'{y:04d}-{m:02d}',
            'label': datetime.date(y, m, 1).strftime('%b'),
            'total': totals.get((y, m), ZERO),
            'partial': (y, m) == (today.year, today.month),
            'selected': (y, m) == (year, month),
        })
    complete = [t['total'] for t in out if not t['partial'] and t['total']]
    return {'months': out, 'avg': (sum(complete, ZERO) / len(complete)) if complete else ZERO}


def fy_summary(group: AccountGroup, fy_start: int, today: datetime.date | None = None) -> dict[str, Any]:
    """Annual financial summary spanning the Indian FY (April to March)."""
    today = today or timezone.localdate()
    start, end = datetime.date(fy_start, 4, 1), datetime.date(fy_start + 1, 3, 31)
    qs = _spend(group, start, end, mail_only=False)
    month_keys = [shift_month(fy_start, 4, i) for i in range(12)]

    by_cat_month = defaultdict(lambda: defaultdict(lambda: ZERO))
    meta: dict[str, dict[str, Any]] = {}
    for row in (qs.values('txn_date__year', 'txn_date__month', 'category__name', 'category__icon', 'category__hue')
                .annotate(t=Sum('amount'), n=Count('id'))):
        name = row['category__name'] or 'Uncategorised'
        by_cat_month[name][(row['txn_date__year'], row['txn_date__month'])] += row['t']
        info = meta.setdefault(name, {
            'icon': row['category__icon'] or 'help',
            'count': 0,
            'hue': row['category__hue'] if row['category__hue'] is not None else 230,
        })
        info['count'] += row['n']

    by_month = defaultdict(lambda: ZERO)
    for per_month in by_cat_month.values():
        for key, amount in per_month.items():
            by_month[key] += amount
    total = sum(by_month.values(), ZERO)

    months = []
    for y, m in month_keys:
        first = datetime.date(y, m, 1)
        months.append({
            'year': y,
            'month': m,
            'param': f'{y:04d}-{m:02d}',
            'label': first.strftime('%b'),
            'full_label': first.strftime('%B %Y'),
            'total': by_month.get((y, m), ZERO),
            'started': first <= today,
            'partial': (y, m) == (today.year, today.month),
        })
    started = [m for m in months if m['started'] and m['total']]
    complete = [m for m in started if not m['partial']]
    peak = max((m['total'] for m in months), default=ZERO)
    for m in months:
        m['bar'] = round(m['total'] / peak * 100) if peak else 0

    # Average over months since tracking began this FY, so a late start doesn't dilute it.
    first_data = next((i for i, m in enumerate(months) if m['total']), 0)
    months_elapsed = max(1, len([m for m in months[first_data:] if m['started']]))
    categories = []
    for name, per_month in sorted(by_cat_month.items(), key=lambda kv: -sum(kv[1].values(), ZERO)):
        cat_total = sum(per_month.values(), ZERO)
        series = [per_month.get(k, ZERO) for k in month_keys]
        top = max(series) or 1
        categories.append({
            'name': name,
            **meta[name],
            'total': cat_total,
            'pct': round(cat_total / total * 100) if total else 0,
            'avg_month': cat_total / months_elapsed,
            'spark': [round(v / top * 100) for v in series],
        })

    stack_names = [c['name'] for c in categories[:STACK_CATEGORIES]]
    stack = [
        {
            'label': c['name'],
            'hue': c['hue'],
            'values': [float(by_cat_month[c['name']].get(k, ZERO)) for k in month_keys],
        }
        for c in categories[:STACK_CATEGORIES]
    ]
    rest = [
        float(sum((v.get(k, ZERO) for n, v in by_cat_month.items() if n not in stack_names), ZERO))
        for k in month_keys
    ]
    if any(rest):
        stack.append({'label': 'Everything else', 'hue': None, 'values': rest})

    # Previous FY over the same stretch of the year, so a part-finished FY compares fairly.
    cutoff = min(end, today)
    prev_total = _sum(_spend(group, datetime.date(fy_start - 1, 4, 1), _same_day_last_year(cutoff), False))
    return {
        'fy_start': fy_start,
        'label': fy_label(fy_start),
        'total': total,
        'months': months,
        'categories': categories,
        'stack': stack,
        'avg_month': (sum((m['total'] for m in complete), ZERO) / len(complete)) if complete else (
            started[0]['total'] if started else ZERO
        ),
        'top_month': max(started, key=lambda m: m['total']) if started else None,
        'prev_label': fy_label(fy_start - 1),
        'prev_total': prev_total,
        'prev_delta_pct': round((total - prev_total) / prev_total * 100) if prev_total else None,
        'in_progress': start <= today <= end,
        'merchants': list(
            qs.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')[:10]
        ),
    }


def available_fys(group: AccountGroup) -> list[int]:
    """Return sorted list of available Indian FY start years for this household."""
    years = {d.year if d.month >= 4 else d.year - 1 for d in live(group).dates('txn_date', 'month')}
    today = timezone.localdate()
    years.add(today.year if today.month >= 4 else today.year - 1)
    return sorted(years)
