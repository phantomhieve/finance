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


SUBSCRIPTION_BRANDS: dict[str, tuple[str, str]] = {
    'NETFLIX': ('Netflix', 'tv'),
    'SPOTIFY': ('Spotify', 'headphones'),
    'HOTSTAR': ('Disney+ Hotstar', 'tv'),
    'JIOHOTSTAR': ('JioHotstar', 'tv'),
    'YOUTUBE': ('YouTube Premium', 'smart_display'),
    'GOOGLEPLAY': ('Google Play', 'play_arrow'),
    'APPLECOM': ('Apple', 'phone_iphone'),
    'ITUNES': ('Apple', 'music_note'),
    'OPENAI': ('OpenAI', 'smart_toy'),
    'CHATGPT': ('OpenAI', 'smart_toy'),
    'AMAZONPRIME': ('Amazon Prime', 'video_camera_front'),
    'PRIMEVIDEO': ('Prime Video', 'video_camera_front'),
    'ICLOUD': ('Apple iCloud', 'cloud'),
    'MICROSOFT': ('Microsoft 365', 'laptop_mac'),
    'SONYLIV': ('SonyLIV', 'tv'),
    'ZEE5': ('ZEE5', 'tv'),
    'AUDIBLE': ('Audible', 'auto_stories'),
    'MEDIUM': ('Medium', 'article'),
    'GITHUB': ('GitHub', 'terminal'),
    'CLAUDE': ('Claude', 'smart_toy'),
}


def _resolve_subscription_service(e: Expense) -> tuple[str, str]:
    """Resolve normalized service display name and icon for a subscription expense."""
    m_key = (e.merchant_key or '').upper()
    if m_key in SUBSCRIPTION_BRANDS:
        return SUBSCRIPTION_BRANDS[m_key]

    raw_text = f'{e.merchant} {e.merchant_raw}'.upper()
    for brand_key, (name, icon) in SUBSCRIPTION_BRANDS.items():
        if brand_key in raw_text:
            return name, icon

    if 'DISNEY' in raw_text:
        return 'Disney+ Hotstar', 'tv'
    if 'APPLE' in raw_text:
        return 'Apple', 'phone_iphone'
    if 'GOOGLE' in raw_text and ('PLAY' in raw_text or 'STORAGE' in raw_text or 'ONE' in raw_text):
        return 'Google One', 'cloud'

    name = e.merchant.strip() if e.merchant else ''
    if not name and e.merchant_raw:
        name = e.merchant_raw.strip()
    if not name:
        name = 'Subscription'
    icon = e.icon or 'subscriptions'
    return name, icon


def subscription_summary(
    group: AccountGroup,
    fy_start: int,
    qs: QuerySet[Expense] | None = None,
    today: datetime.date | None = None,
    month_keys: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Month-wise recurring subscription metrics and cadence matrix across the Indian FY."""
    today = today or timezone.localdate()
    start = datetime.date(fy_start, 4, 1)
    end = datetime.date(fy_start + 1, 3, 31)
    if qs is None:
        qs = _spend(group, start, end, mail_only=False)
    if month_keys is None:
        month_keys = [shift_month(fy_start, 4, i) for i in range(12)]

    sub_q = Q(category__name__icontains='subscription') | Q(merchant_key__in=SUBSCRIPTION_BRANDS.keys())
    for term in ('netflix', 'spotify', 'hotstar', 'youtube', 'openai', 'chatgpt', 'prime video', 'amazon prime'):
        sub_q |= Q(merchant__icontains=term)

    sub_expenses = list(
        qs.filter(sub_q)
        .exclude(refunded_amount__gte=F('amount'), amount__gt=ZERO)
        .select_related('category', 'payment_source')
        .order_by('txn_date', 'id')
    )

    by_month_items: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    by_service: dict[str, dict[str, Any]] = defaultdict(lambda: {
        'name': '',
        'icon': 'subscriptions',
        'total': ZERO,
        'count': 0,
        'latest_amount': ZERO,
        'by_month': defaultdict(lambda: ZERO),
    })

    total_spend = ZERO
    total_count = 0

    for e in sub_expenses:
        net = max(ZERO, e.amount - (e.refunded_amount or ZERO))
        if net <= ZERO:
            continue
        svc_name, svc_icon = _resolve_subscription_service(e)
        key = (e.txn_date.year, e.txn_date.month)
        item = {
            'id': e.pk,
            'service': svc_name,
            'merchant': e.merchant,
            'icon': svc_icon,
            'amount': net,
            'txn_date': e.txn_date,
            'day_label': e.txn_date.strftime('%d %b'),
            'payment_source': e.payment_source.display_name if e.payment_source else '',
        }
        by_month_items[key].append(item)
        total_spend += net
        total_count += 1

        rec = by_service[svc_name]
        rec['name'] = svc_name
        rec['icon'] = svc_icon
        rec['total'] += net
        rec['count'] += 1
        rec['latest_amount'] = net
        rec['by_month'][key] += net

    months = []
    for y, m in month_keys:
        first = datetime.date(y, m, 1)
        m_items = by_month_items.get((y, m), [])
        m_total = sum((it['amount'] for it in m_items), ZERO)
        months.append({
            'year': y,
            'month': m,
            'param': f'{y:04d}-{m:02d}',
            'label': first.strftime('%b'),
            'full_label': first.strftime('%B %Y'),
            'total': m_total,
            'count': len(m_items),
            'items': m_items,
            'started': first <= today,
            'partial': (y, m) == (today.year, today.month),
        })

    started_months = [m for m in months if m['started']]
    active_months_count = max(1, len(started_months))
    avg_month = (total_spend / Decimal(str(active_months_count))).quantize(Decimal('0.01')) if started_months else ZERO

    services = []
    for svc_name, rec in sorted(by_service.items(), key=lambda kv: -kv[1]['total']):
        months_data = []
        months_active = 0
        for y, m in month_keys:
            amt = rec['by_month'].get((y, m), ZERO)
            is_paid = amt > ZERO
            if is_paid:
                months_active += 1
            first = datetime.date(y, m, 1)
            months_data.append({
                'year': y,
                'month': m,
                'param': f'{y:04d}-{m:02d}',
                'label': first.strftime('%b'),
                'amount': amt,
                'paid': is_paid,
                'started': first <= today,
            })
        services.append({
            'name': svc_name,
            'icon': rec['icon'],
            'total': rec['total'],
            'count': rec['count'],
            'latest_amount': rec['latest_amount'],
            'months_active': months_active,
            'months_data': months_data,
        })

    return {
        'total': total_spend,
        'count': total_count,
        'services_count': len(services),
        'avg_month': avg_month,
        'months': months,
        'services': services,
        'has_subscriptions': total_spend > ZERO or len(sub_expenses) > 0,
    }


def fy_summary(
    group: AccountGroup,
    fy_start: int,
    today: datetime.date | None = None,
    hide_investments: bool = False,
) -> dict[str, Any]:
    """Annual financial summary spanning the Indian FY (April to March)."""
    today = today or timezone.localdate()
    start, end = datetime.date(fy_start, 4, 1), datetime.date(fy_start + 1, 3, 31)
    qs = _spend(group, start, end, mail_only=False)
    if hide_investments:
        qs = qs.exclude(category__name=INVESTMENT_CATEGORY)
    month_keys = [shift_month(fy_start, 4, i) for i in range(12)]

    by_cat_month = defaultdict(lambda: defaultdict(lambda: ZERO))
    month_counts: dict[tuple[int, int], int] = defaultdict(int)
    month_cat_totals: dict[tuple[int, int], list[tuple[Decimal, str, str, int]]] = defaultdict(list)
    meta: dict[str, dict[str, Any]] = {}
    for row in (
        qs.values(
            'txn_date__year',
            'txn_date__month',
            'category__id',
            'category__name',
            'category__icon',
            'category__hue',
        ).annotate(t=Sum('amount'), n=Count('id'))
    ):
        name = row['category__name'] or 'Uncategorised'
        key = (row['txn_date__year'], row['txn_date__month'])
        icon = row['category__icon'] or 'help'
        hue = row['category__hue'] if row['category__hue'] is not None else 230
        by_cat_month[name][key] += row['t']
        month_counts[key] += row['n']
        month_cat_totals[key].append((row['t'], name, icon, hue))
        info = meta.setdefault(name, {
            'id': row['category__id'],
            'icon': icon,
            'count': 0,
            'hue': hue,
        })
        info['count'] += row['n']

    by_month = defaultdict(lambda: ZERO)
    for per_month in by_cat_month.values():
        for key, amount in per_month.items():
            by_month[key] += amount
    total = sum(by_month.values(), ZERO)
    total_count = sum(month_counts.values())

    months = []
    for y, m in month_keys:
        first = datetime.date(y, m, 1)
        m_total = by_month.get((y, m), ZERO)
        cat_candidates = month_cat_totals.get((y, m), [])
        top_c = max(cat_candidates, key=lambda x: x[0]) if cat_candidates else None
        months.append({
            'year': y,
            'month': m,
            'param': f'{y:04d}-{m:02d}',
            'label': first.strftime('%b'),
            'full_label': first.strftime('%B %Y'),
            'total': m_total,
            'count': month_counts.get((y, m), 0),
            'started': first <= today,
            'partial': (y, m) == (today.year, today.month),
            'top_cat': top_c[1] if top_c else '',
            'top_cat_icon': top_c[2] if top_c else '',
            'top_cat_hue': top_c[3] if top_c else 230,
        })
    started = [m for m in months if m['started'] and m['total']]
    complete = [m for m in started if not m['partial']]
    peak = max((m['total'] for m in months), default=ZERO)
    avg_month_val = (
        (sum((m['total'] for m in complete), ZERO) / len(complete))
        if complete
        else (started[0]['total'] if started else ZERO)
    )
    for m in months:
        m['bar'] = round(m['total'] / peak * 100) if peak else 0
        m['is_peak'] = bool(peak > ZERO and m['total'] == peak)
        m['vs_avg_pct'] = (
            round((m['total'] - avg_month_val) / avg_month_val * 100)
            if (avg_month_val > ZERO and m['started'] and m['total'] > ZERO)
            else None
        )

    # Previous FY over the same stretch of the year, so a part-finished FY compares fairly.
    cutoff = min(end, today)
    prev_qs = _spend(group, datetime.date(fy_start - 1, 4, 1), _same_day_last_year(cutoff), False)
    if hide_investments:
        prev_qs = prev_qs.exclude(category__name=INVESTMENT_CATEGORY)
    prev_total = _sum(prev_qs)
    prev_by_cat = {
        (name or 'Uncategorised'): amt
        for name, amt in prev_qs.values_list('category__name').annotate(t=Sum('amount'))
        if amt
    }

    # Average over months since tracking began this FY, so a late start doesn't dilute it.
    first_data = next((i for i, m in enumerate(months) if m['total']), 0)
    months_elapsed = max(1, len([m for m in months[first_data:] if m['started']]))
    categories = []
    for name, per_month in sorted(by_cat_month.items(), key=lambda kv: -sum(kv[1].values(), ZERO)):
        cat_total = sum(per_month.values(), ZERO)
        series = [per_month.get(k, ZERO) for k in month_keys]
        top = max(series) or 1
        prev_cat = prev_by_cat.get(name, ZERO)
        delta_cat = cat_total - prev_cat
        spark_months = []
        for (y, m), v in zip(month_keys, series):
            first = datetime.date(y, m, 1)
            spark_months.append({
                'label': first.strftime('%b'),
                'param': f'{y:04d}-{m:02d}',
                'amount': v,
                'pct': round(v / top * 100) if v else 0,
                'started': first <= today,
            })
        categories.append({
            'name': name,
            **meta[name],
            'total': cat_total,
            'pct': round(cat_total / total * 100) if total else 0,
            'avg_month': cat_total / months_elapsed,
            'spark': [round(v / top * 100) for v in series],
            'spark_months': spark_months,
            'active_months': sum(1 for v in series if v > ZERO),
            'prev': prev_cat,
            'delta': delta_cat,
            'gap': abs(delta_cat),
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

    # Annual highlight insights (day-to-day burn, biggest buy, most visited, top riser)
    flexible = qs.exclude(category__name__in=FIXED_CATEGORIES)
    elapsed_days = max(1, (min(end, today) - start).days + 1) if today >= start else 1
    per_day = (_sum(flexible) / Decimal(str(elapsed_days))) if total > ZERO else ZERO
    biggest = (
        flexible.select_related('category').order_by('-amount').first()
        or qs.select_related('category').order_by('-amount').first()
    )
    frequent = (
        flexible.exclude(merchant='')
        .values('merchant')
        .annotate(total=Sum('amount'), count=Count('id'), latest_date=models.Max('txn_date'))
        .filter(count__gte=2)
        .order_by('-count', '-total')
        .first()
    )
    if frequent and frequent.get('latest_date'):
        frequent['month_param'] = frequent['latest_date'].strftime('%Y-%m')
    risers = [c for c in categories if c['prev'] > ZERO and c['delta'] >= RISER_FLOOR]
    riser = max(risers, key=lambda c: c['delta']) if risers else None

    raw_merchants = list(
        qs.exclude(merchant='')
        .values('merchant')
        .annotate(total=Sum('amount'), count=Count('id'), latest_date=models.Max('txn_date'))
        .order_by('-total')[:10]
    )
    top_merchant_total = raw_merchants[0]['total'] if raw_merchants else ZERO
    merchants = []
    for m_row in raw_merchants:
        m_tot = m_row['total'] or ZERO
        m_cnt = m_row['count'] or 1
        latest_dt = m_row.get('latest_date')
        merchants.append({
            'merchant': m_row['merchant'],
            'total': m_tot,
            'count': m_cnt,
            'avg': (m_tot / Decimal(str(m_cnt))).quantize(Decimal('1')),
            'pct': round(m_tot / total * 100) if total else 0,
            'bar': round(m_tot / top_merchant_total * 100) if top_merchant_total else 0,
            'month_param': latest_dt.strftime('%Y-%m') if latest_dt else f'{fy_start:04d}-04',
        })

    # Payment sources & household members breakdown
    source_rows = list(
        qs.values('payment_source__id')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    source_map = PaymentSource.objects.in_bulk([r['payment_source__id'] for r in source_rows if r['payment_source__id']])
    top_source_total = source_rows[0]['total'] if source_rows else ZERO
    sources = []
    for row in source_rows:
        ps = source_map.get(row['payment_source__id'])
        s_tot = row['total'] or ZERO
        sources.append({
            'name': ps.display_name if ps else 'Manual / Cash & UPI',
            'short_name': ps.short_name if ps else 'Manual / UPI',
            'icon': ps.icon if ps else 'wallet',
            'kind': ps.kind if ps else 'MANUAL',
            'total': s_tot,
            'count': row['count'],
            'pct': round(s_tot / total * 100) if total else 0,
            'bar': round(s_tot / top_source_total * 100) if top_source_total else 0,
        })

    members = []
    for row in (
        qs.values('member__id', 'member__first_name', 'member__username')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    ):
        m_tot = row['total'] or ZERO
        members.append({
            'id': row['member__id'],
            'name': row['member__first_name'] or row['member__username'] or 'Shared / unassigned',
            'total': m_tot,
            'count': row['count'],
            'pct': round(m_tot / total * 100) if total else 0,
        })

    subscriptions = subscription_summary(group, fy_start, qs=qs, today=today, month_keys=month_keys)
    subscriptions['share_pct'] = round(float(subscriptions['total'] / total * 100), 1) if total > ZERO else 0
    low_candidates = complete if len(complete) >= 2 else (started if len(started) >= 2 else [])
    low_month = min(low_candidates, key=lambda m: m['total']) if low_candidates else None
    latest_active_month = started[-1]['param'] if started else f'{fy_start:04d}-04'

    return {
        'fy_start': fy_start,
        'start': start,
        'end': end,
        'label': fy_label(fy_start),
        'total': total,
        'count': total_count,
        'months': months,
        'started_months_count': len([m for m in months if m['started']]),
        'active_months_count': len(started),
        'complete_months_count': len(complete),
        'latest_month_param': latest_active_month,
        'categories': categories,
        'stack': stack,
        'avg_month': avg_month_val,
        'top_month': max(started, key=lambda m: m['total']) if started else None,
        'low_month': low_month,
        'per_day': per_day,
        'biggest': biggest,
        'biggest_month_param': biggest.txn_date.strftime('%Y-%m') if biggest else latest_active_month,
        'frequent': frequent,
        'riser': riser,
        'prev_label': fy_label(fy_start - 1),
        'prev_total': prev_total,
        'prev_delta': total - prev_total,
        'prev_gap': abs(total - prev_total),
        'prev_delta_pct': round((total - prev_total) / prev_total * 100) if prev_total else None,
        'in_progress': start <= today <= end,
        'merchants': merchants,
        'sources': sources,
        'members': members,
        'subscriptions': subscriptions,
    }


def available_fys(group: AccountGroup) -> list[int]:
    """Return sorted list of available Indian FY start years for this household."""
    years = {d.year if d.month >= 4 else d.year - 1 for d in live(group).dates('txn_date', 'month')}
    today = timezone.localdate()
    years.add(today.year if today.month >= 4 else today.year - 1)
    return sorted(years)
