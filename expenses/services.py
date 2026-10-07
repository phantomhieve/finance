"""Business logic for the expense tracker: categories, learning, ingestion and summaries."""
import calendar
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from pftracker.utils import fy_label

from . import ai
from .models import CardStatement, Expense, ExpenseCategory, MerchantRule, PaymentSource
from .parsing import brand_category, mask_sensitive, normalize_merchant

ZERO = Decimal('0')
RISER_FLOOR = Decimal('500')
# Fixed monthly costs are left out of "day-to-day" figures so rent doesn't drown everything else.
FIXED_CATEGORIES = ('Rent & Housing', 'EMI & Loans', 'Insurance')
# Investment debits reveal the portfolio, so they are only shown to people who can see it.
INVESTMENT_CATEGORY = 'Investments'
STACK_CATEGORIES = 5

# name, kind, icon, hue
DEFAULT_CATEGORIES = [
    ('Food & Dining', 'SPEND', 'restaurant', 20),
    ('Groceries', 'SPEND', 'local_grocery_store', 120),
    ('Shopping', 'SPEND', 'shopping_bag', 300),
    ('Transport', 'SPEND', 'local_taxi', 200),
    ('Fuel', 'SPEND', 'local_gas_station', 30),
    ('Bills & Utilities', 'SPEND', 'receipt_long', 45),
    ('Rent & Housing', 'SPEND', 'home', 260),
    ('Household & Services', 'SPEND', 'cleaning_services', 170),
    ('Health', 'SPEND', 'medical_services', 0),
    ('Personal Care', 'SPEND', 'spa', 320),
    ('Entertainment', 'SPEND', 'movie', 335),
    ('Subscriptions', 'SPEND', 'subscriptions', 280),
    ('Travel', 'SPEND', 'flight', 190),
    ('Education', 'SPEND', 'school', 230),
    ('Kids', 'SPEND', 'child_care', 50),
    ('Insurance', 'SPEND', 'shield', 210),
    ('EMI & Loans', 'SPEND', 'account_balance', 15),
    ('Gifts & Donations', 'SPEND', 'redeem', 345),
    ('Fees & Charges', 'SPEND', 'request_quote', 5),
    ('Cash Withdrawal', 'SPEND', 'local_atm', 100),
    ('Other', 'SPEND', 'category', 230),
    ('Investments', 'TRANSFER', 'trending_up', 150),
    ('Transfers', 'TRANSFER', 'swap_horiz', 215),
    ('Credit Card Payment', 'TRANSFER', 'credit_score', 250),
    ('Income & Refunds', 'INCOME', 'savings', 140),
]


def ensure_default_categories(group):
    existing = set(ExpenseCategory.objects.filter(group=group).values_list('name', flat=True))
    missing = [
        ExpenseCategory(group=group, name=name, kind=kind, icon=icon, hue=hue, sort_order=i * 10)
        for i, (name, kind, icon, hue) in enumerate(DEFAULT_CATEGORIES)
        if name not in existing
    ]
    if missing:
        ExpenseCategory.objects.bulk_create(missing, ignore_conflicts=True)


def categories_by_name(group):
    ensure_default_categories(group)
    return {c.name: c for c in ExpenseCategory.objects.filter(group=group)}


# ---------------------------------------------------------------------------
# Categorisation + learning
# ---------------------------------------------------------------------------

def _rule_for(group, merchant_key):
    if not merchant_key:
        return None
    return MerchantRule.objects.select_related('category').filter(group=group, merchant_key=merchant_key).first()


def categorise_expense(expense, cats=None):
    """Assign a category without AI: learned rule → built-in brand/keyword → income default.

    Leaves category None (source NONE) when nothing matches so the AI batch can pick it up.
    """
    cats = cats or categories_by_name(expense.group)
    rule = _rule_for(expense.group, expense.merchant_key)
    if rule:
        expense.category = rule.category
        expense.category_source = 'RULE' if rule.source == 'USER' else 'AI'
        expense.category_confidence = 1.0 if rule.source == 'USER' else None
        MerchantRule.objects.filter(pk=rule.pk).update(hits=rule.hits + 1)
        return
    name = brand_category(expense.merchant_key, f'{expense.merchant} {expense.merchant_raw}')
    if not name and expense.channel == 'ATM':
        name = 'Cash Withdrawal'
    if not name and expense.direction == 'CREDIT':
        name = 'Income & Refunds'
    if name and name in cats:
        expense.category = cats[name]
        expense.category_source = 'KEYWORD'
        expense.category_confidence = 0.7


def ai_categorise_pending(group, limit=200):
    """Ask Gemini to categorise uncategorised rows; cache confident answers as AI rules."""
    pending = list(
        Expense.objects.filter(group=group, is_deleted=False, category__isnull=True, category_source='NONE')
        .order_by('-txn_date')[:limit]
    )
    if not pending or not ai.ai_available():
        return 0
    cats = categories_by_name(group)
    examples = list(
        MerchantRule.objects.filter(group=group, source='USER').select_related('category')
        .order_by('-updated_at').values_list('merchant_label', 'category__name')[:40]
    )
    by_key = {}
    items = []
    for e in pending:
        bucket_key = e.merchant_key or f'#{e.pk}'
        if bucket_key in by_key:
            by_key[bucket_key].append(e)
            continue
        by_key[bucket_key] = [e]
        items.append({
            'id': e.pk, 'merchant': e.merchant or e.merchant_raw or '(unknown)', 'raw': e.merchant_raw,
            'amount': float(e.amount), 'direction': e.direction, 'channel': e.channel,
        })
    answers = ai.categorise(items, list(cats), [list(x) for x in examples])
    updated = 0
    for item in items:
        answer = answers.get(item['id'])
        if not answer:
            continue
        name, confidence = answer
        if name not in cats:
            continue
        lead = next(e for e in pending if e.pk == item['id'])
        group_rows = by_key[lead.merchant_key or f'#{lead.pk}']
        for e in group_rows:
            e.category = cats[name]
            e.category_source = 'AI'
            e.category_confidence = confidence
            e.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])
            updated += 1
        if lead.merchant_key and confidence >= 0.6:
            MerchantRule.objects.get_or_create(
                group=group, merchant_key=lead.merchant_key,
                defaults={'category': cats[name], 'source': 'AI', 'merchant_label': lead.merchant},
            )
    return updated


@transaction.atomic
def learn_category(expense, category, user, apply_to_similar=True):
    """User picked a category: remember it for this merchant and re-file past non-user rows."""
    expense.category = category
    expense.category_source = 'USER'
    expense.category_confidence = 1.0
    expense.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])
    if not expense.merchant_key or not apply_to_similar:
        return 0
    MerchantRule.objects.update_or_create(
        group=expense.group, merchant_key=expense.merchant_key,
        defaults={'category': category, 'source': 'USER', 'created_by': user,
                  'merchant_label': expense.merchant or expense.merchant_key},
    )
    return (
        Expense.objects.filter(group=expense.group, merchant_key=expense.merchant_key)
        .exclude(pk=expense.pk).exclude(category_source__in=('USER', 'MATCH'))
        .update(category=category, category_source='RULE', category_confidence=1.0)
    )


SETTLE_WINDOW_DAYS = 3


def _statement_paid_by(statement, debit, window):
    if statement.paid_amount == debit.amount and statement.paid_at and abs((statement.paid_at - debit.txn_date).days) <= window.days:
        return True
    issued = statement.statement_date or statement.created_at.date()
    due = statement.due_date or issued + datetime.timedelta(days=20)
    return statement.total_due == debit.amount and issued - window <= debit.txn_date <= due + window


def settle_internal_movements(group, since):
    """Re-file money that only moved between the household's own accounts, so it is never counted as spend.

    - a bank debit equal to a card statement's paid / total amount is that card's bill payment
      (the purchases on the card are already counted);
    - a debit matched by an equal credit into another of the household's accounts is a self-transfer.
    Returns the ids of re-filed debits.
    """
    cats = categories_by_name(group)
    bill, transfer = cats.get('Credit Card Payment'), cats.get('Transfers')
    window = datetime.timedelta(days=SETTLE_WINDOW_DAYS)
    open_rows = (live(group).filter(txn_date__gte=since - window, currency='INR')
                 .exclude(source='MANUAL').exclude(category_source__in=('USER', 'MATCH')))
    debits = list(open_rows.filter(direction='DEBIT').exclude(payment_source__kind='CREDIT_CARD'))
    if not debits:
        return []
    statements = list(CardStatement.objects.filter(group=group, created_at__date__gte=since - datetime.timedelta(days=60)))
    credits = list(open_rows.filter(direction='CREDIT', payment_source__isnull=False))
    settled, used_credits = [], set()

    def refile(expense, category):
        expense.category, expense.category_source, expense.category_confidence = category, 'MATCH', 1.0
        expense.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])

    for debit in debits:
        if bill and any(_statement_paid_by(st, debit, window) for st in statements):
            refile(debit, bill)
            settled.append(debit.pk)
            continue
        if not transfer or not debit.payment_source_id:
            continue
        twin = next((c for c in credits if c.pk not in used_credits and c.amount == debit.amount
                     and c.payment_source_id != debit.payment_source_id
                     and abs((c.txn_date - debit.txn_date).days) <= 1), None)
        if twin:
            used_credits.add(twin.pk)
            refile(debit, transfer)
            refile(twin, transfer)
            settled.append(debit.pk)
    return settled


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def resolve_payment_source(group, instrument, institution, last4, owner=None):
    if not (institution or last4):
        return None
    kind = instrument if instrument in dict(PaymentSource.KIND_CHOICES) else 'OTHER'
    source, created = PaymentSource.objects.get_or_create(
        group=group, kind=kind, institution=institution or '', last4=last4 or '',
        defaults={'owner': owner, 'is_auto': True},
    )
    return source


def build_expense(group, parsed, *, source, member=None, gmail_account=None, message_id='',
                  subject='', dedupe_key='', statement=None, cats=None):
    """Create (and categorise) an Expense from a ParsedTransaction. Returns (expense, created)."""
    if dedupe_key:
        existing = Expense.objects.filter(group=group, dedupe_key=dedupe_key).first()
        if existing:
            return existing, False
    payment_source = resolve_payment_source(group, parsed.instrument, parsed.institution, parsed.last4, member)
    merchant = parsed.merchant
    if not merchant and parsed.channel == 'ATM':
        merchant = 'Cash withdrawal'
    expense = Expense(
        group=group, amount=parsed.amount, currency=parsed.currency, direction=parsed.direction,
        txn_date=parsed.txn_date, txn_time=parsed.txn_time,
        merchant=merchant or 'Unknown merchant', merchant_raw=parsed.merchant_raw[:255],
        merchant_key=parsed.merchant_key, payment_source=payment_source, channel=parsed.channel,
        reference=parsed.reference[:64], source=source, gmail_account=gmail_account,
        gmail_message_id=message_id, email_subject=mask_sensitive(subject or '')[:255], dedupe_key=dedupe_key,
        statement=statement, member=member or (payment_source.owner if payment_source else None),
    )
    categorise_expense(expense, cats)
    expense.save()
    return expense, True


def manual_merchant(expense):
    """Recompute display/key after a manual merchant edit."""
    display, key = normalize_merchant(expense.merchant)
    expense.merchant_key = key
    if not expense.merchant_raw:
        expense.merchant_raw = expense.merchant


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def spend_q():
    """Debits that count as spending (uncategorised debits count until filed elsewhere)."""
    return Q(direction='DEBIT') & (Q(category__isnull=True) | Q(category__kind='SPEND'))


def live(group):
    return Expense.objects.filter(group=group, is_deleted=False)


def month_bounds(year, month):
    return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])


def shift_month(year, month, delta):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _sum(qs):
    return qs.aggregate(t=Sum('amount'))['t'] or ZERO


def _daily(qs, days):
    by_day = defaultdict(lambda: ZERO)
    for d, amt in qs.values_list('txn_date', 'amount'):
        by_day[d.day] += amt
    return [by_day.get(d, ZERO) for d in range(1, days + 1)]


def _spend(group, start, end, mail_only):
    qs = live(group).filter(txn_date__gte=start, txn_date__lte=end, currency='INR').filter(spend_q())
    return qs.exclude(source='MANUAL') if mail_only else qs


def month_summary(group, year, month, mail_only=False, today=None, hide_investments=False):
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
            'day': elapsed, 'days': days, 'prev_to_date': prev_to_date,
            'delta': total - prev_to_date, 'gap': abs(total - prev_to_date),
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
            'id': row['category__id'], 'name': name,
            'icon': row['category__icon'] or 'help', 'hue': row['category__hue'] if row['category__hue'] is not None else 230,
            'total': row['total'], 'count': row['count'],
            'pct': round(row['total'] / total * 100) if total else 0,
            'prev': prev, 'delta': row['total'] - prev, 'gap': abs(row['total'] - prev),
        })

    members = []
    for row in (spend_qs.values('member__id', 'member__first_name', 'member__username')
                .annotate(total=Sum('amount'), count=Count('id')).order_by('-total')):
        members.append({
            'id': row['member__id'],
            'name': row['member__first_name'] or row['member__username'] or 'Shared / unassigned',
            'total': row['total'], 'count': row['count'],
            'pct': round(row['total'] / total * 100) if total else 0,
        })

    sources = []
    source_rows = list(spend_qs.values('payment_source__id').annotate(total=Sum('amount'), count=Count('id'))
                       .order_by('-total'))
    source_map = PaymentSource.objects.in_bulk([r['payment_source__id'] for r in source_rows if r['payment_source__id']])
    for row in source_rows:
        ps = source_map.get(row['payment_source__id'])
        sources.append({'name': ps.display_name if ps else 'Unknown / manual', 'icon': ps.icon if ps else 'wallet',
                        'total': row['total'], 'count': row['count']})

    merchants = list(
        spend_qs.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')[:8]
    )
    risers = [c for c in categories if c['delta'] >= RISER_FLOOR]
    flexible = spend_qs.exclude(category__name__in=FIXED_CATEGORIES)
    frequent = (flexible.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
                .filter(count__gte=2).order_by('-count', '-total').first())

    return {
        'year': year, 'month': month, 'start': start, 'end': end,
        'label': start.strftime('%B %Y'),
        'prev_label': p_start.strftime('%B'),
        'total': total,
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


def monthly_trend(group, year, month, n=6, mail_only=False, today=None):
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
            'year': y, 'month': m, 'param': f'{y:04d}-{m:02d}',
            'label': datetime.date(y, m, 1).strftime('%b'),
            'total': totals.get((y, m), ZERO),
            'partial': (y, m) == (today.year, today.month),
            'selected': (y, m) == (year, month),
        })
    complete = [t['total'] for t in out if not t['partial'] and t['total']]
    return {'months': out, 'avg': (sum(complete, ZERO) / len(complete)) if complete else ZERO}


def fy_summary(group, fy_start, today=None):
    today = today or timezone.localdate()
    start, end = datetime.date(fy_start, 4, 1), datetime.date(fy_start + 1, 3, 31)
    qs = _spend(group, start, end, mail_only=False)
    month_keys = [shift_month(fy_start, 4, i) for i in range(12)]

    by_cat_month = defaultdict(lambda: defaultdict(lambda: ZERO))
    meta = {}
    for row in (qs.values('txn_date__year', 'txn_date__month', 'category__name', 'category__icon', 'category__hue')
                .annotate(t=Sum('amount'), n=Count('id'))):
        name = row['category__name'] or 'Uncategorised'
        by_cat_month[name][(row['txn_date__year'], row['txn_date__month'])] += row['t']
        info = meta.setdefault(name, {'icon': row['category__icon'] or 'help', 'count': 0,
                                      'hue': row['category__hue'] if row['category__hue'] is not None else 230})
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
            'year': y, 'month': m, 'param': f'{y:04d}-{m:02d}', 'label': first.strftime('%b'),
            'full_label': first.strftime('%B %Y'), 'total': by_month.get((y, m), ZERO),
            'started': first <= today, 'partial': (y, m) == (today.year, today.month),
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
            'name': name, **meta[name], 'total': cat_total,
            'pct': round(cat_total / total * 100) if total else 0,
            'avg_month': cat_total / months_elapsed,
            'spark': [round(v / top * 100) for v in series],
        })

    stack_names = [c['name'] for c in categories[:STACK_CATEGORIES]]
    stack = [{'label': c['name'], 'hue': c['hue'],
              'values': [float(by_cat_month[c['name']].get(k, ZERO)) for k in month_keys]}
             for c in categories[:STACK_CATEGORIES]]
    rest = [float(sum((v.get(k, ZERO) for n, v in by_cat_month.items() if n not in stack_names), ZERO))
            for k in month_keys]
    if any(rest):
        stack.append({'label': 'Everything else', 'hue': None, 'values': rest})

    # Previous FY over the same stretch of the year, so a part-finished FY compares fairly.
    cutoff = min(end, today)
    prev_total = _sum(_spend(group, datetime.date(fy_start - 1, 4, 1), _same_day_last_year(cutoff), False))
    return {
        'fy_start': fy_start, 'label': fy_label(fy_start), 'total': total, 'months': months,
        'categories': categories, 'stack': stack,
        'avg_month': (sum((m['total'] for m in complete), ZERO) / len(complete)) if complete else (
            started[0]['total'] if started else ZERO),
        'top_month': max(started, key=lambda m: m['total']) if started else None,
        'prev_label': fy_label(fy_start - 1),
        'prev_total': prev_total,
        'prev_delta_pct': round((total - prev_total) / prev_total * 100) if prev_total else None,
        'in_progress': start <= today <= end,
        'merchants': list(qs.exclude(merchant='').values('merchant').annotate(total=Sum('amount'), count=Count('id'))
                          .order_by('-total')[:10]),
    }


def _same_day_last_year(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def available_fys(group):
    years = {d.year if d.month >= 4 else d.year - 1 for d in live(group).dates('txn_date', 'month')}
    today = timezone.localdate()
    years.add(today.year if today.month >= 4 else today.year - 1)
    return sorted(years)
