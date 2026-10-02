"""Context builders for the scheduled portfolio emails (monthly review, weekly brief)."""
import os

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.utils import timezone as _tz

import datetime
from decimal import Decimal

from pftracker.utils import fy_label, pct
from .models import CashPosition, FinancialGoal, FixedDeposit, MonthlySnapshot, StockHolding
from .services import _fy_opening_snapshot, get_portfolio_summary

DRAWDOWN_PCT = -10
OUTPERFORMER_PCT = 15


def app_url(path=''):
    """Public base URL for links in emails: VAULT_PUBLIC_URL, else the first https CSRF origin."""
    base = os.environ.get('VAULT_PUBLIC_URL', '').strip()
    if not base:
        base = next((o for o in settings.CSRF_TRUSTED_ORIGINS if o.startswith('https://')), '')
    return base.rstrip('/') + path if base else ''


def send_html_email(subject, text, html, to):
    from_email = getattr(settings, 'EMAIL_HOST_USER', '') or 'vault@example.com'
    msg = EmailMultiAlternatives(subject, text, from_email, to)
    msg.attach_alternative(html, 'text/html')
    msg.send()


def build_monthly_context(group, insights):
    summary = get_portfolio_summary(group)
    total = summary['total_value']
    invested = summary['total_invested']

    since = None
    # The cron snapshots on day 1 just before this email; compare against the previous month's.
    month_start = _tz.localdate().replace(day=1)
    last = (MonthlySnapshot.objects.filter(group=group, month__lt=month_start)
            .order_by('-month').first())
    if last is not None and last.total_current_value:
        change = total - last.total_current_value
        money_added = invested - last.total_invested
        since = {
            'month': last.month,
            'change': change,
            'change_pct': pct(change, last.total_current_value),
            'money_added': money_added,
            'market': change - money_added,
        }

    roadmap = summary.get('goal_roadmap') or {}
    allocation = sorted(
        (c for c in summary['consolidated'] if c['value']),
        key=lambda c: c['value'], reverse=True,
    )
    return {
        'month': _tz.now().strftime('%B %Y'),
        'as_of': _tz.localtime().strftime('%d %b %Y'),
        'total_value': total,
        'total_invested': invested,
        'total_returns': summary['total_returns'],
        'return_pct': summary['return_pct'],
        'since': since,
        'fy': summary.get('fy_performance'),
        'goal': roadmap.get('spotlight'),
        'goal_fy': roadmap.get('cur_fy_label'),
        'allocation': allocation,
        'insights': insights,
        'app_url': app_url('/portfolio/'),
    }


def build_weekly_context(group):
    cash = float(CashPosition.objects.filter(group=group, is_baby=False)
                 .aggregate(t=Sum('amount'))['t'] or 0)
    fds = FixedDeposit.objects.filter(group=group, is_active=True, is_baby=False)
    fd = sum(float(f.current_value) for f in fds)

    by_symbol = {}
    for s in StockHolding.objects.filter(account__group=group, is_baby=False).select_related('account'):
        row = by_symbol.setdefault(s.symbol, {'symbol': s.symbol, 'invested': 0.0, 'current': 0.0, 'accounts': []})
        row['invested'] += float(s.purchase_value)
        row['current'] += float(s.current_value)
        row['accounts'].append({'name': s.account.name, 'qty': s.quantity})

    stocks = []
    for s in by_symbol.values():
        s['pnl'] = s['current'] - s['invested']
        s['pnl_pct'] = (s['pnl'] / s['invested'] * 100) if s['invested'] else 0
        s['flag'] = ('drawdown' if s['pnl_pct'] <= DRAWDOWN_PCT
                     else 'outperformer' if s['pnl_pct'] >= OUTPERFORMER_PCT else '')
        stocks.append(s)
    stocks.sort(key=lambda x: x['pnl_pct'])

    inv = sum(s['invested'] for s in stocks)
    cur = sum(s['current'] for s in stocks)
    return {
        'date': _tz.localtime().strftime('%d %B %Y'),
        'total_cash': cash,
        'total_fd': fd,
        'total_liquid': cash + fd,
        'stocks': stocks,
        'notable': [s for s in stocks if s['flag']],
        'drawdowns': sum(1 for s in stocks if s['flag'] == 'drawdown'),
        'outperformers': sum(1 for s in stocks if s['flag'] == 'outperformer'),
        'equity_invested': inv,
        'equity_current': cur,
        'equity_pnl': cur - inv,
        'equity_pnl_pct': ((cur - inv) / inv * 100) if inv else 0,
        'app_url': app_url('/portfolio/'),
    }


_CATEGORY_LABELS = {'fd': 'Fixed deposits', 'epf': 'EPF', 'nps': 'NPS', 'us_stocks_(rsu)': 'US stocks (RSU)'}


def _category_label(key):
    return _CATEGORY_LABELS.get(key) or key.replace('_', ' ').capitalize()


def build_fy_review_context(group, fy_start):
    """Year-in-review for a closed FY: opening → March close, money vs market, goal verdict."""
    label = fy_label(fy_start)
    opening = _fy_opening_snapshot(group, fy_start)
    closing = MonthlySnapshot.objects.filter(group=group, month=datetime.date(fy_start + 1, 3, 1)).first()

    if closing is not None:
        close_value, close_invested, close_data, close_is_live = (
            closing.total_current_value, closing.total_invested, closing.data or {}, False)
    else:
        summary = get_portfolio_summary(group)
        close_value, close_invested, close_data, close_is_live = (
            summary['total_value'], summary['total_invested'], {}, True)

    year = None
    if opening is not None:
        change = close_value - opening.total_current_value
        money_added = close_invested - opening.total_invested
        market = change - money_added
        year = {
            'opening_value': opening.total_current_value,
            'opening_month': opening.month,
            'change': change,
            'change_pct': pct(change, opening.total_current_value),
            'money_added': money_added,
            'market': market,
            'market_pct': pct(market, opening.total_current_value),
        }

    snaps = list(MonthlySnapshot.objects.filter(
        group=group, month__gte=datetime.date(fy_start, 4, 1), month__lte=datetime.date(fy_start + 1, 3, 1),
    ).order_by('month'))
    peak = max((float(s.total_current_value) for s in snaps), default=0)
    path = [{'month': s.month, 'value': s.total_current_value,
             'bar': round(float(s.total_current_value) / peak * 100) if peak else 0} for s in snaps]
    with_returns = [s for s in snaps if s.returns_this_month]
    best = max(with_returns, key=lambda s: s.returns_this_month, default=None)
    worst = min(with_returns, key=lambda s: s.returns_this_month, default=None)

    movers = []
    open_data = (opening.data or {}) if opening is not None else {}
    for key, cur in close_data.items():
        if not isinstance(cur, dict) or 'current' not in cur:
            continue
        before = float((open_data.get(key) or {}).get('current') or 0)
        delta = float(cur['current']) - before
        if abs(delta) >= 1:
            movers.append({'name': _category_label(key), 'value': cur['current'], 'delta': delta})
    movers.sort(key=lambda m: abs(m['delta']), reverse=True)

    goals = []
    for g in FinancialGoal.objects.filter(group=group, financial_year=label).order_by('target_amount'):
        ref = g.closing_value if g.closing_value is not None else close_value
        achieved = ref >= g.target_amount
        goals.append({
            'label': g.label, 'target': g.target_amount, 'achieved': achieved,
            'pct': round(min(float(ref) / float(g.target_amount) * 100, 999), 1) if g.target_amount else 0,
            'diff': ref - g.target_amount,
        })
    hit = sum(1 for g in goals if g['achieved'])
    verdict = ('none' if not goals else 'achieved' if hit == len(goals) else 'partial' if hit else 'missed')

    next_label = fy_label(fy_start + 1)
    next_goals = []
    for g in FinancialGoal.objects.filter(group=group, financial_year=next_label).order_by('target_amount'):
        gap = max(Decimal('0'), g.target_amount - close_value)
        next_goals.append({'label': g.label, 'target': g.target_amount, 'gap': gap,
                           'monthly': (gap / 12).quantize(Decimal('1')),
                           'growth_pct': pct(gap, close_value)})

    return {
        'fy': label,
        'next_fy': next_label,
        'close_value': close_value,
        'close_invested': close_invested,
        'close_is_live': close_is_live,
        'year': year,
        'path': path,
        'best': best,
        'worst': worst if worst is not None and worst != best else None,
        'movers': movers[:6],
        'goals': goals,
        'goals_hit': hit,
        'verdict': verdict,
        'next_goals': next_goals,
        'as_of': _tz.localtime().strftime('%d %b %Y'),
        'app_url': app_url('/portfolio/#goals-section'),
    }


def apply_floor(ctx, floor):
    liquid = ctx['total_liquid']
    ctx['floor'] = floor
    ctx['deficit'] = max(0.0, floor - liquid)
    ctx['deployable'] = max(0.0, liquid - floor)
    ctx['coverage_pct'] = round(liquid / floor * 100) if floor else 100
    ctx['coverage_bar'] = min(100, ctx['coverage_pct'])
    return ctx
