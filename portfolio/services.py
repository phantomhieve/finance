import datetime
import logging
import re
from decimal import Decimal

import cloudscraper
import requests
from django.conf import settings
from django.db.models import Case, F, Sum, When
from django.utils import timezone

from pftracker.utils import (
    ZERO as _ZERO, ROUND2 as _ROUND2, pct as _pct,
    fy_start_year, fy_label, get_google_credentials,
)
from .models import (
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding,
    CommodityPrice, MonthlySnapshot, FinancialGoal,
    USStockHolding, RealEstateHolding,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _sum_qs(qs, field):
    return qs.aggregate(t=Sum(field))['t'] or _ZERO


def _parse_inr(value):
    """Parse '₹15,981', '₹2,75,000', '1234.56', or '' → Decimal (returns _ZERO on failure)."""
    if not value:
        return _ZERO
    cleaned = str(value).replace('\u20b9', '').replace('₹', '').replace(',', '').replace(' ', '').strip()
    if cleaned in ('-', '', '—'):
        return _ZERO
    try:
        return Decimal(cleaned)
    except Exception:
        return _ZERO


# ---------------------------------------------------------------------------
# Shared query helpers
# ---------------------------------------------------------------------------

def _gf(model_qs, group):
    """Filter a queryset by group. If group is None, return unfiltered (backward compat)."""
    if group is None:
        return model_qs
    return model_qs.filter(group=group)


def get_commodity_summary(group=None, is_baby=False):
    """Aggregate commodity holdings into gold/silver weights, values, and P&L."""
    prices = {p.commodity_type: p for p in CommodityPrice.objects.filter(
        commodity_type__in=('GOLD', 'SILVER'),
    )}
    gold_price = prices.get('GOLD')
    silver_price = prices.get('SILVER')
    gold_rate = gold_price.rate_per_gram if gold_price else _ZERO
    silver_rate = silver_price.rate_per_gram if silver_price else _ZERO

    gold_qs = _gf(CommodityHolding.objects.filter(commodity_type='GOLD', is_baby=is_baby), group)
    silver_qs = _gf(CommodityHolding.objects.filter(commodity_type='SILVER', is_baby=is_baby), group)
    gold_weight = _sum_qs(gold_qs, 'weight_grams')
    silver_weight = _sum_qs(silver_qs, 'weight_grams')
    gold_value = (gold_weight * gold_rate).quantize(_ROUND2) if gold_rate else _ZERO
    silver_value = (silver_weight * silver_rate).quantize(_ROUND2) if silver_rate else _ZERO
    total = gold_value + silver_value

    invested = _gf(CommodityHolding.objects.filter(is_baby=is_baby), group).aggregate(
        t=Sum(F('weight_grams') * F('purchase_price_per_gram'))
    )['t'] or _ZERO

    return {
        'gold_price_obj': gold_price,
        'silver_price_obj': silver_price,
        'gold_rate': gold_rate,
        'silver_rate': silver_rate,
        'gold_weight': gold_weight,
        'silver_weight': silver_weight,
        'gold_value': gold_value,
        'silver_value': silver_value,
        'commodity_total': total,
        'commodity_invested': invested,
        'commodity_returns': total - invested,
    }


def _zerodha_account_sums(z_accounts, is_baby=False):
    """Batch-fetch per-account current/purchase sums for stocks and MFs (6 queries → dict)."""
    def _agg(qs, field):
        return dict(qs.values_list('account_id').annotate(t=Sum(field)))

    stock_qs = StockHolding.objects.filter(account__in=z_accounts, is_baby=is_baby)
    index_qs = MutualFundHolding.objects.filter(account__in=z_accounts, fund_type='INDEX', is_baby=is_baby)
    other_qs = MutualFundHolding.objects.filter(account__in=z_accounts, fund_type='OTHER', is_baby=is_baby)

    maps = {
        'stocks_cur': _agg(stock_qs, 'current_value'),
        'stocks_inv': _agg(stock_qs, 'purchase_value'),
        'index_cur': _agg(index_qs, 'current_value'),
        'index_inv': _agg(index_qs, 'purchase_value'),
        'other_cur': _agg(other_qs, 'current_value'),
        'other_inv': _agg(other_qs, 'purchase_value'),
    }
    result = {}
    for key, mapping in maps.items():
        for acct_id, val in mapping.items():
            result.setdefault(acct_id, {})[key] = val
    return result


# ---------------------------------------------------------------------------
# FY goals roadmap
# ---------------------------------------------------------------------------

def _fy_opening_snapshot(group, fy_start):
    """Snapshot closest to the start of an FY: prior March, else first snapshot inside the FY."""
    qs = _gf(MonthlySnapshot.objects, group)
    snap = qs.filter(month=datetime.date(fy_start, 3, 1)).first()
    if snap is None:
        snap = qs.filter(
            month__gte=datetime.date(fy_start, 4, 1),
            month__lte=datetime.date(fy_start + 1, 3, 1),
        ).order_by('month').first()
    return snap


def get_fy_performance(group, total_value, total_invested, today=None, exclude_real_estate=False):
    """FY-to-date change split into fresh money vs market gains (needs an opening snapshot)."""
    today = today or datetime.date.today()
    fy = fy_start_year(today)
    opening = _fy_opening_snapshot(group, fy)
    if opening is None:
        return None
    opening_value, opening_invested = opening.total_current_value, opening.total_invested
    if exclude_real_estate:
        re = (opening.data or {}).get('real_estate')
        if not re or 'current' not in re:
            return None  # totals-only snapshot: can't separate real estate out
        opening_value -= Decimal(str(re.get('current', 0)))
        opening_invested -= Decimal(str(re.get('invested', 0)))
    change = total_value - opening_value
    money_added = total_invested - opening_invested
    market_gain = change - money_added
    return {
        'label': fy_label(fy),
        'opening_value': opening_value,
        'opening_month': opening.month,
        'change': change,
        'change_pct': _pct(change, opening_value),
        'money_added': money_added,
        'market_gain': market_gain,
    }


_PACE_BAND = 5  # progress-vs-time lead/lag (pct points) still counted as "on track"


def _months_until(today, deadline):
    return max(1, round((deadline - today).days / 30.44)) if deadline and deadline > today else 1


def build_goal_roadmap(group, total_value, today=None):
    """Group portfolio goals by Indian FY with a frozen achieved/missed verdict for closed years.

    - Closed FY:  judged on ``closing_value`` (March snapshot), else on ``achieved_at`` ≤ FY end.
    - Current FY: live value; pace compares progress since FY open against time elapsed.
    - Future FY / Long term: live value, required monthly growth to the deadline.

    Side effect: stamps ``achieved_at`` the first time an open goal is reached and clears it
    if the portfolio falls back below target before the FY closes. Closed goals are never touched.
    """
    today = today or datetime.date.today()
    total = float(total_value)
    cur_fy = fy_start_year(today)
    cur_start = datetime.date(cur_fy, 4, 1)
    cur_end = datetime.date(cur_fy + 1, 3, 31)
    total_days = (cur_end - cur_start).days + 1
    time_pct = round(min(100.0, ((today - cur_start).days + 1) / total_days * 100), 1)
    days_left = max(0, (cur_end - today).days)

    goal_objs = list(_gf(FinancialGoal.objects, group))
    march_close = {}
    if any(g.fy_start is not None and g.fy_start < cur_fy and g.closing_value is None for g in goal_objs):
        march_close = {
            s.month.year - 1: s.total_current_value
            for s in _gf(MonthlySnapshot.objects, group).filter(month__month=3)
        }
    opening_snap = _fy_opening_snapshot(group, cur_fy)
    opening_value = float(opening_snap.total_current_value) if opening_snap else None

    goals = []
    for g in goal_objs:
        target = float(g.target_amount)
        fy_s = g.fy_start
        if fy_s is None:
            state, fy_name = 'long_term', FinancialGoal.LONG_TERM
        else:
            fy_name = fy_label(fy_s)
            state = 'closed' if fy_s < cur_fy else 'current' if fy_s == cur_fy else 'future'

        item = {
            'id': g.id,
            'label': g.label,
            'target': target,
            'target_date': g.target_date,
            'fy': fy_name,
            'fy_start': fy_s,
            'state': state,
            'notes': g.notes,
            'achieved_at': g.achieved_at,
        }

        if state == 'closed':
            closing = g.closing_value if g.closing_value is not None else march_close.get(fy_s)
            if closing is not None:
                achieved = float(closing) >= target
                item['closing_value'] = float(closing)
            else:
                achieved = g.achieved_at is not None and g.achieved_at <= g.fy_end_date
                item['closing_value'] = None
            ref = item['closing_value'] if item['closing_value'] is not None else total
            item['status'] = 'achieved' if achieved else 'missed'
        else:
            achieved = total >= target
            ref = total
            if achieved and g.achieved_at is None:
                g.achieved_at = today
                FinancialGoal.objects.filter(pk=g.pk).update(achieved_at=today)
            elif not achieved and g.achieved_at is not None:
                g.achieved_at = None
                FinancialGoal.objects.filter(pk=g.pk).update(achieved_at=None)
            item['achieved_at'] = g.achieved_at
            item['status'] = 'achieved' if achieved else ('on_track' if state == 'current' else 'upcoming')

        item['achieved'] = achieved
        item['pct'] = round(min(ref / target * 100, 100), 1) if target else 0
        item['remaining'] = max(0.0, target - ref)
        item['surplus'] = max(0.0, ref - target)

        if state != 'closed' and not achieved:
            deadline = g.target_date or g.fy_end_date
            if deadline:
                item['months_left'] = _months_until(today, deadline)
                item['monthly_needed'] = round(item['remaining'] / item['months_left'])

        if state == 'current':
            item['time_pct'] = time_pct
            item['days_left'] = days_left
            if opening_value is not None and target > opening_value:
                progress = (total - opening_value) / (target - opening_value) * 100
                item['fy_progress_pct'] = round(max(0.0, min(progress, 100.0)), 1)
                item['expected_today'] = opening_value + (target - opening_value) * time_pct / 100
                item['vs_expected'] = total - item['expected_today']
            else:
                item['fy_progress_pct'] = item['pct']
            if not achieved:
                lead = item['fy_progress_pct'] - time_pct
                item['lead_pct'] = round(lead, 1)
                if lead >= _PACE_BAND:
                    item['status'] = 'ahead'
                elif lead <= -_PACE_BAND:
                    item['status'] = 'behind'
        goals.append(item)

    goals.sort(key=lambda x: (x['fy_start'] if x['fy_start'] is not None else 9999, x['target']))

    years = {}
    for item in goals:
        years.setdefault(item['fy'], {'label': item['fy'], 'state': item['state'], 'fy_start': item['fy_start'], 'goals': []})['goals'].append(item)
    for y in years.values():
        y['achieved'] = sum(1 for x in y['goals'] if x['achieved'])
        y['total'] = len(y['goals'])
        y['top_target'] = max(x['target'] for x in y['goals'])
        if y['state'] == 'closed':
            y['closing_value'] = next((x['closing_value'] for x in y['goals'] if x.get('closing_value') is not None), None)
            y['verdict'] = 'achieved' if y['achieved'] == y['total'] else 'partial' if y['achieved'] else 'missed'

    current_year = next((y for y in years.values() if y['state'] == 'current'), None)
    spotlight = None
    if current_year:
        pending = [x for x in current_year['goals'] if not x['achieved']]
        spotlight = pending[0] if pending else current_year['goals'][-1]

    closed = sorted((y for y in years.values() if y['state'] == 'closed'), key=lambda y: y['fy_start'], reverse=True)
    upcoming = [y for y in years.values() if y['state'] in ('future', 'long_term')]

    return {
        'goals': goals,
        'today': today,
        'cur_fy_label': fy_label(cur_fy),
        'cur_fy_end': cur_end,
        'time_pct': time_pct,
        'days_left': days_left,
        'opening_value': opening_value,
        'current_year': current_year,
        'spotlight': spotlight,
        'upcoming': upcoming,
        'closed': closed,
        'track_record': {
            'hit': sum(y['achieved'] for y in closed),
            'total': sum(y['total'] for y in closed),
        },
    }


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------

def without_real_estate(summary, group):
    """Re-base headline totals, allocation and FY performance on the portfolio minus real estate.

    Goals are left on the full portfolio: their targets are net-worth targets.
    """
    total_value = summary['total_value'] - summary['real_estate_current']
    total_invested = summary['total_invested'] - summary['real_estate_invested']
    total_returns = total_value - total_invested
    return {
        **summary,
        'total_value': total_value,
        'total_invested': total_invested,
        'total_returns': total_returns,
        'return_pct': _pct(total_returns, total_invested),
        'assets': [dict(a, pct=_pct(a['value'], total_value))
                   for a in summary['assets'] if a['name'] != 'Real Estate'],
        'consolidated': [dict(c, pct=_pct(c['value'], total_value))
                         for c in summary['consolidated'] if c['name'] != 'Real Estate'],
        'fy_performance': summary['fy_performance'] and get_fy_performance(
            group, total_value, total_invested, exclude_real_estate=True),
    }


def get_portfolio_summary(group=None, is_baby=False):
    """Aggregate every asset class into a master portfolio summary dict, scoped to group."""

    acct_ids = ZerodhaAccount.objects.filter(group=group).values_list('id', flat=True) if group else None
    if acct_ids is not None:
        stocks_qs = StockHolding.objects.filter(account_id__in=acct_ids, is_baby=is_baby)
        index_mf_qs = MutualFundHolding.objects.filter(account_id__in=acct_ids, fund_type='INDEX', is_baby=is_baby)
        other_mf_qs = MutualFundHolding.objects.filter(account_id__in=acct_ids, fund_type='OTHER', is_baby=is_baby)
    else:
        stocks_qs = StockHolding.objects.filter(is_baby=is_baby)
        index_mf_qs = MutualFundHolding.objects.filter(fund_type='INDEX', is_baby=is_baby)
        other_mf_qs = MutualFundHolding.objects.filter(fund_type='OTHER', is_baby=is_baby)

    all_stocks_purchased = _sum_qs(stocks_qs, 'purchase_value')
    all_stocks_current = _sum_qs(stocks_qs, 'current_value')
    index_purchased = _sum_qs(index_mf_qs, 'purchase_value')
    index_current = _sum_qs(index_mf_qs, 'current_value')
    other_purchased = _sum_qs(other_mf_qs, 'purchase_value')
    other_current = _sum_qs(other_mf_qs, 'current_value')

    if not is_baby:
        epf_agg = _gf(EPFEntry.objects, group).aggregate(
            contrib=Sum(Case(When(entry_type='CONTRIBUTION', then='amount'))),
            interest=Sum(Case(When(entry_type='INTEREST', then='amount'))),
        )
        epf_total_contrib = epf_agg['contrib'] or _ZERO
        epf_total_interest = epf_agg['interest'] or _ZERO
        epf_balance = epf_total_contrib + epf_total_interest

        nps_qs = _gf(NPSEntry.objects, group)
        nps_latest = nps_qs.order_by('-date', '-created_at').first()
        nps_balance = nps_latest.total_balance if nps_latest else _ZERO
        nps_agg = nps_qs.aggregate(
            contrib=Sum('contribution'), interest=Sum('interest_earned'),
        )
        nps_total_contrib = nps_agg['contrib'] or _ZERO
        nps_total_interest = nps_agg['interest'] or _ZERO
    else:
        epf_total_contrib = _ZERO
        epf_total_interest = _ZERO
        epf_balance = _ZERO
        nps_latest = None
        nps_balance = _ZERO
        nps_total_contrib = _ZERO
        nps_total_interest = _ZERO

    active_fds = list(_gf(FixedDeposit.objects.filter(is_active=True, is_baby=is_baby), group))
    fd_principal = sum(fd.principal for fd in active_fds)
    fd_current = sum(fd.current_value for fd in active_fds)

    cash_total = _sum_qs(_gf(CashPosition.objects.filter(is_baby=is_baby), group).all(), 'amount')
    bonds_total = _sum_qs(_gf(BondHolding.objects.filter(is_baby=is_baby), group).all(), 'amount')

    crypto_qs = _gf(CryptoHolding.objects.filter(is_baby=is_baby), group).all()
    crypto_invested = _sum_qs(crypto_qs, 'amount_invested')
    crypto_current = _sum_qs(crypto_qs, 'current_value')

    us_stocks = list(_gf(USStockHolding.objects.filter(is_baby=is_baby), group).all())
    us_stocks_invested = sum((h.purchase_value for h in us_stocks), _ZERO)
    us_stocks_current = sum((h.current_value for h in us_stocks), _ZERO)

    real_estate_holdings = list(_gf(RealEstateHolding.objects.filter(is_baby=is_baby), group).all())
    real_estate_invested = sum((h.total_cost_basis for h in real_estate_holdings), _ZERO)
    real_estate_current = sum((h.current_value for h in real_estate_holdings), _ZERO)

    comm = get_commodity_summary(group, is_baby=is_baby)
    gold_value = comm['gold_value']
    silver_value = comm['silver_value']
    commodity_total = comm['commodity_total']
    commodity_invested = comm['commodity_invested']

    # Asset-class list
    assets = [
        {'name': 'EPF', 'value': epf_balance, 'icon': 'account_balance'},
        {'name': 'Index Funds', 'value': index_current, 'icon': 'trending_up'},
        {'name': 'Cash', 'value': cash_total, 'icon': 'payments'},
        {'name': 'Individual Stocks', 'value': all_stocks_current, 'icon': 'candlestick_chart'},
        {'name': 'Other Mutual Funds', 'value': other_current, 'icon': 'pie_chart'},
        {'name': 'Gold', 'value': gold_value, 'icon': 'diamond'},
        {'name': 'Silver', 'value': silver_value, 'icon': 'toll'},
        {'name': 'NPS', 'value': nps_balance, 'icon': 'assured_workload'},
        {'name': 'Crypto', 'value': crypto_current, 'icon': 'currency_bitcoin'},
        {'name': 'FD', 'value': fd_current, 'icon': 'lock'},
        {'name': 'Bonds', 'value': bonds_total, 'icon': 'receipt_long'},
        {'name': 'US Stocks (RSU)', 'value': us_stocks_current, 'icon': 'work'},
        {'name': 'Real Estate', 'value': real_estate_current, 'icon': 'domain'},
    ]
    total_value = sum(a['value'] for a in assets)
    for a in assets:
        a['pct'] = _pct(a['value'], total_value)
    assets.sort(key=lambda a: a['value'], reverse=True)

    # Equity breakdown
    equity_total = index_current + all_stocks_current + other_current + nps_balance + us_stocks_current
    equity_invested = index_purchased + all_stocks_purchased + other_purchased + nps_total_contrib + us_stocks_invested
    equity_returns = equity_total - equity_invested
    equity_items = [
        {'name': 'Index Funds', 'value': index_current},
        {'name': 'Individual Stocks', 'value': all_stocks_current},
        {'name': 'Other Mutual Funds', 'value': other_current},
        {'name': 'NPS', 'value': nps_balance},
        {'name': 'US Stocks (RSU)', 'value': us_stocks_current},
    ]
    for e in equity_items:
        e['pct'] = _pct(e['value'], equity_total)

    # Consolidated portfolio
    debt_total = epf_balance + fd_current + bonds_total
    consolidated = [
        {'name': 'Equity', 'value': equity_total},
        {'name': 'Debt Instruments', 'value': debt_total},
        {'name': 'Real Estate', 'value': real_estate_current},
        {'name': 'Cash', 'value': cash_total},
        {'name': 'Commodity', 'value': commodity_total},
        {'name': 'Crypto', 'value': crypto_current},
    ]
    for c in consolidated:
        c['pct'] = _pct(c['value'], total_value)

    # Invested vs returns
    total_invested = (
        all_stocks_purchased + index_purchased + other_purchased
        + epf_total_contrib + nps_total_contrib
        + fd_principal + cash_total + bonds_total + crypto_invested
        + commodity_invested + us_stocks_invested + real_estate_invested
    )
    total_returns = total_value - total_invested
    return_pct = _pct(total_returns, total_invested)

    # Goals are household-level targets against the master portfolio only
    roadmap = build_goal_roadmap(group, total_value) if not is_baby else None

    # Zerodha account summaries (prefetch totals to avoid N+1)
    z_accounts = _gf(ZerodhaAccount.objects, group).all() if group else ZerodhaAccount.objects.all()
    acct_sums = _zerodha_account_sums(z_accounts, is_baby=is_baby)
    accounts = []
    for acct in z_accounts:
        rec = acct_sums.get(acct.id, {})
        s = rec.get('stocks_cur', _ZERO)
        i = rec.get('index_cur', _ZERO)
        o = rec.get('other_cur', _ZERO)
        current = s + i + o
        invested = rec.get('stocks_inv', _ZERO) + rec.get('index_inv', _ZERO) + rec.get('other_inv', _ZERO)
        accounts.append({
            'account': acct,
            'stocks': s,
            'index_mf': i,
            'other_mf': o,
            'total': current,
            'invested': invested,
            'returns': current - invested,
        })

    return {
        'assets': assets,
        'total_value': total_value,
        'total_invested': total_invested,
        'total_returns': total_returns,
        'return_pct': return_pct,
        'equity_items': equity_items,
        'equity_total': equity_total,
        'equity_invested': equity_invested,
        'equity_returns': equity_returns,
        'consolidated': consolidated,
        'goals': roadmap['goals'] if roadmap else [],
        'goal_roadmap': roadmap,
        'fy_performance': None if is_baby else get_fy_performance(group, total_value, total_invested),
        'accounts': accounts,
        'epf_balance': epf_balance,
        'epf_total_contrib': epf_total_contrib,
        'epf_total_interest': epf_total_interest,
        'nps_latest': nps_latest,
        'nps_total_contrib': nps_total_contrib,
        'nps_total_interest': nps_total_interest,
        'active_fds': sorted(active_fds, key=lambda fd: fd.current_value, reverse=True),
        'fd_principal': fd_principal,
        'fd_current': fd_current,
        'cash_positions': _gf(CashPosition.objects.filter(is_baby=is_baby), group).order_by('-amount'),
        'cash_total': cash_total,
        'bonds': _gf(BondHolding.objects.filter(is_baby=is_baby), group).order_by('-amount'),
        'bonds_total': bonds_total,
        'crypto_holdings': _gf(CryptoHolding.objects.filter(is_baby=is_baby), group).order_by('-current_value'),
        'crypto_invested': crypto_invested,
        'crypto_current': crypto_current,
        'gold_holdings': _gf(CommodityHolding.objects.filter(commodity_type='GOLD', is_baby=is_baby), group),
        'silver_holdings': _gf(CommodityHolding.objects.filter(commodity_type='SILVER', is_baby=is_baby), group),
        **{k: comm[k] for k in (
            'gold_rate', 'silver_rate', 'gold_weight', 'silver_weight',
            'gold_value', 'silver_value', 'commodity_total',
            'commodity_invested', 'commodity_returns',
            'gold_price_obj', 'silver_price_obj',
        )},
        'epf_entries': [] if is_baby else _gf(EPFEntry.objects, group).all()[:10],
        'nps_entries': [] if is_baby else _gf(NPSEntry.objects, group).all()[:10],
        'us_stocks': us_stocks,
        'us_stocks_invested': us_stocks_invested,
        'us_stocks_current': us_stocks_current,
        'us_stocks_returns': us_stocks_current - us_stocks_invested,
        'real_estate_holdings': real_estate_holdings,
        'real_estate_invested': real_estate_invested,
        'real_estate_current': real_estate_current,
        'real_estate_returns': real_estate_current - real_estate_invested,
    }


# ---------------------------------------------------------------------------
# Google Sheets sync
# ---------------------------------------------------------------------------

def sync_zerodha_from_sheets(account=None, group=None):
    """
    Read Zerodha holdings from Google Sheets and upsert into DB.
    If account is None, sync all accounts (optionally filtered by group).
    """
    try:
        import gspread
    except ImportError:
        raise RuntimeError("gspread is not installed. Run: pip install gspread google-auth")

    # Per-household credential resolution
    creds = get_google_credentials(group)
    if isinstance(creds, dict):
        gc = gspread.service_account_from_dict(creds)
    else:
        gc = gspread.service_account(filename=creds)
    if account:
        accounts = [account]
    else:
        qs = ZerodhaAccount.objects.exclude(sheet_id='')
        if group:
            qs = qs.filter(group=group)
        accounts = qs
    results = []

    for acct in accounts:
        if not acct.sheet_id:
            continue
        try:
            spreadsheet = gc.open_by_key(acct.sheet_id)
        except Exception as e:
            logger.error("Failed to open sheet for %s: %s", acct.name, e)
            results.append({'account': acct.name, 'error': str(e)})
            continue

        synced = {'account': acct.name, 'stocks': 0, 'index_mf': 0, 'other_mf': 0}

        if acct.sheet_range_stocks:
            synced['stocks'] = _sync_stocks(acct, spreadsheet, acct.sheet_range_stocks)
        if acct.sheet_range_index_mf:
            synced['index_mf'] = _sync_mf(acct, spreadsheet, acct.sheet_range_index_mf, 'INDEX')
        if acct.sheet_range_other_mf:
            synced['other_mf'] = _sync_mf(acct, spreadsheet, acct.sheet_range_other_mf, 'OTHER')

        acct.last_synced = timezone.now()
        acct.save(update_fields=['last_synced'])
        results.append(synced)

    return results


def _get_worksheet_rows(spreadsheet, range_name, acct_name, label):
    """Open a worksheet by range_name and return all rows, or [] on failure."""
    try:
        sheet_name = range_name.split('!')[0] if '!' in range_name else range_name
        return spreadsheet.worksheet(sheet_name).get_all_values()
    except Exception as e:
        logger.error("Failed to read %s for %s: %s", label, acct_name, e)
        return []


def _norm_cell(v) -> str:
    """Normalize a sheet cell for section/header detection."""
    s = (v or "").strip().lower()
    # common emoji / bullets in section headers
    s = s.replace("📈", "").replace("📊", "").replace("•", "").strip()
    return s


def _slice_section_rows(all_rows, section_keyword: str):
    """
    Slice out data rows for a given section from a single worksheet that contains
    multiple sections (Stocks + Index MFs + Other MFs).
    """
    if not all_rows:
        return []

    section_keyword = section_keyword.lower()
    start_idx = None
    for i, row in enumerate(all_rows):
        first = _norm_cell(row[0] if row else "")
        if section_keyword in first:
            start_idx = i
            break
    if start_idx is None:
        return []

    # header is typically the next non-empty row
    header_idx = None
    for i in range(start_idx + 1, min(start_idx + 8, len(all_rows))):
        row = all_rows[i]
        if any(_norm_cell(c) for c in row):
            header_idx = i
            break
    if header_idx is None:
        return []

    data = []
    for row in all_rows[header_idx + 1:]:
        first = _norm_cell(row[0] if row else "")
        # stop at blank spacer row
        if not any(_norm_cell(c) for c in row):
            break
        # stop at next section header
        if ("mutual funds" in first) or ("stock holdings" in first):
            break
        data.append(row)
    return data


def _sync_stocks(acct, spreadsheet, range_name):
    all_rows = _get_worksheet_rows(spreadsheet, range_name, acct.name, 'stocks')
    rows = _slice_section_rows(all_rows, "stock holdings") or all_rows
    if not rows:
        return 0

    baby_symbols = set(StockHolding.objects.filter(account=acct, is_baby=True).values_list('symbol', flat=True))
    StockHolding.objects.filter(account=acct).delete()
    bulk = []
    for row in rows:
        if len(row) < 5:
            continue
        symbol = str(row[0]).strip()
        if not symbol or symbol.lower() in ('symbol', 'stock', '\U0001f4c8'):
            continue
        # Guard against non-symbol strings that would violate DB constraints.
        # (Real ticker symbols should be short; long values usually mean header/notes.)
        if len(symbol) > 50:
            continue
        try:
            qty = int(float(str(row[1]).replace(',', '').strip() or '0'))
        except (ValueError, TypeError):
            continue
        bulk.append(StockHolding(
            account=acct, symbol=symbol, quantity=qty,
            purchase_value=_parse_inr(row[2]),
            current_value=_parse_inr(row[3]),
            is_baby=symbol in baby_symbols
        ))
    if bulk:
        StockHolding.objects.bulk_create(bulk)
    return len(bulk)


def _sync_mf(acct, spreadsheet, range_name, fund_type):
    all_rows = _get_worksheet_rows(spreadsheet, range_name, acct.name, f'MF-{fund_type}')
    section = "index mutual funds" if fund_type == "INDEX" else "other mutual funds"
    rows = _slice_section_rows(all_rows, section) or all_rows
    if not rows:
        return 0

    baby_funds = set(MutualFundHolding.objects.filter(account=acct, fund_type=fund_type, is_baby=True).values_list('fund_name', flat=True))
    MutualFundHolding.objects.filter(account=acct, fund_type=fund_type).delete()
    bulk = []
    for row in rows:
        if len(row) < 5:
            continue
        fund_name = str(row[0]).strip()
        fn = fund_name.lower()
        if not fund_name or fn in ('fund', 'scheme', '\U0001f4ca'):
            continue
        # Skip section headers accidentally captured as data rows.
        if ("mutual funds" in fn) or ("stock holdings" in fn):
            continue
        try:
            units = Decimal(str(row[1]).replace(',', '').strip() or '0')
        except Exception:
            continue
        bulk.append(MutualFundHolding(
            account=acct, fund_name=fund_name, fund_type=fund_type,
            units=units,
            purchase_value=_parse_inr(row[2]),
            current_value=_parse_inr(row[3]),
            is_baby=fund_name in baby_funds
        ))
    if bulk:
        MutualFundHolding.objects.bulk_create(bulk)
    return len(bulk)


# ---------------------------------------------------------------------------
# Commodity price refresh
#   Priority 1: goodreturns.in via cloudscraper (India city scrape - free, no key)
#   Priority 2: gold-api.com (global spot, no key, troy-oz → gram conversion + India tax adjustment)
# ---------------------------------------------------------------------------

_TROY_OZ_TO_GRAMS = 31.1035

# As of 2026, India effective import duty is 15% (10% BCD + 5% AIDC) plus 3% GST/IGST.
# We apply a ~18.45% tax adjustment factor (1.1845) to convert global spot to local India retail price.
_INDIA_COMMODITY_TAX_ADJUSTMENT = 1.1845

_GOODRETURNS_CITY = getattr(settings, 'COMMODITY_CITY', 'jaipur')

_COMMODITY_CONFIG = {
    'GOLD': {
        'path': 'gold-rates',
        'json_key': 'gold_price_24K',
        'json_key_alt': 'current_price_24K',
        'gold_api_symbol': 'XAU',
    },
    'SILVER': {
        'path': 'silver-rates',
        'json_key': 'silver_price_1G',
        'json_key_alt': None,
        'gold_api_symbol': 'XAG',
    },
}

_scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'darwin'})


def refresh_commodity_prices():
    """
    Fetch latest gold (24K) and silver prices (per gram, INR) and persist.
    Returns e.g. {'gold': 9850.0, 'silver': 105.0}.

    Source priority:
      1. goodreturns.in — India city-wise scrape (free, no key needed)
      2. gold-api.com — global spot converted to INR (free, no key needed) + Indian tax adjustment (~18.45%)
    """
    today = datetime.date.today().isoformat()
    results = {}

    for ctype, cfg in _COMMODITY_CONFIG.items():
        rate = (
            _fetch_goodreturns_rate(cfg, today)
            or _fetch_gold_api_rate(cfg)
        )
        if rate:
            CommodityPrice.objects.update_or_create(
                commodity_type=ctype,
                defaults={'rate_per_gram': rate, 'fetched_at': timezone.now()},
            )
            results[ctype.lower()] = float(rate)

    return results


def _fetch_gold_api_rate(cfg):
    """Fetch price per gram in INR from api.gold-api.com (free, no key).
    Uses global spot price (LBMA) and applies India customs duty & tax adjustment (~18.45%)."""
    symbol = cfg.get('gold_api_symbol')
    if not symbol:
        return None
    try:
        resp = requests.get(
            f'https://api.gold-api.com/price/{symbol}/INR',
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("gold-api.com %s returned %s", symbol, resp.status_code)
            return None
        data = resp.json()
        price_per_oz = data.get('price')
        if not price_per_oz or price_per_oz <= 0:
            return None
        rate_global = price_per_oz / _TROY_OZ_TO_GRAMS
        rate_india = round(rate_global * _INDIA_COMMODITY_TAX_ADJUSTMENT, 2)
        logger.info("gold-api.com %s: ₹%.2f/gram (adjusted global spot)", symbol, rate_india)
        return rate_india
    except Exception as e:
        logger.warning("gold-api.com %s fetch failed: %s", symbol, e)
        return None


def _fetch_goodreturns_rate(cfg, date_str):
    """Fallback: fetch from goodreturns.in via cloudscraper."""
    url = f"https://www.goodreturns.in/{cfg['path']}/{_GOODRETURNS_CITY}.html"

    try:
        resp = _scraper.get(
            url,
            params={'gr_db_dynamic_content': 'metal_past_price', 'date': date_str},
            headers={'X-OIGT-Header': 'GITPL', 'Referer': url},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get(cfg['json_key']) or (
                data.get(cfg['json_key_alt']) if cfg['json_key_alt'] else None
            )
            rate = _parse_inr(raw)
            if rate > 0:
                return rate
    except Exception:
        pass

    try:
        resp = _scraper.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("goodreturns.in %s HTML returned %s", cfg['path'], resp.status_code)
            return None
        html = resp.text
        rate = _extract_price_from_html(html, cfg.get('html_pattern'))
        if rate and rate > 0:
            return rate
        logger.warning("goodreturns.in %s: could not extract price from HTML", cfg['path'])
        return None
    except Exception as e:
        logger.warning("goodreturns.in %s fetch failed: %s", cfg['path'], e)
        return None


_HTML_PRICE_PATTERNS = [
    re.compile(r'(?:&#x20b9;|₹)\s*([\d,]+)\s*</strong>\s*per\s*gram', re.I),
    re.compile(r'today\s+is\s+(?:&#x20b9;|₹)\s*([\d,]+(?:\.\d+)?)\s*per\s*gram', re.I),
    re.compile(r'today\s+is\s+<strong>(?:&#x20b9;|₹)\s*([\d,]+(?:\.\d+)?)</strong>\s*per\s*gram', re.I),
    re.compile(r'per\s*gram[^<]*?(?:&#x20b9;|₹)\s*([\d,]+(?:\.\d+)?)', re.I),
]


def _extract_price_from_html(html, extra_pattern=None):
    """Extract per-gram price from goodreturns HTML page."""
    patterns = list(_HTML_PRICE_PATTERNS)
    if extra_pattern:
        patterns.insert(0, re.compile(extra_pattern, re.I))
    for pat in patterns:
        m = pat.search(html)
        if m:
            return _parse_inr(m.group(1))
    return None


# ---------------------------------------------------------------------------
# US stock price refresh (RSU holdings like Uber)
# ---------------------------------------------------------------------------

def _fetch_usd_inr_rate():
    """Fetch the current USD → INR exchange rate from a free API."""
    for url in (
        'https://open.er-api.com/v6/latest/USD',
        'https://api.exchangerate-api.com/v4/latest/USD',
    ):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                rate = resp.json().get('rates', {}).get('INR')
                if rate and rate > 0:
                    logger.info("USD/INR rate: %.2f (from %s)", rate, url)
                    return round(rate, 2)
        except Exception as e:
            logger.warning("USD/INR fetch from %s failed: %s", url, e)
    return None


def _fetch_stock_price_usd(symbol):
    """Fetch the current stock price in USD via Yahoo Finance chart API."""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.status_code != 200:
            logger.warning("Yahoo Finance %s returned %s", symbol, resp.status_code)
            return None
        data = resp.json()
        meta = data.get('chart', {}).get('result', [{}])[0].get('meta', {})
        price = meta.get('regularMarketPrice')
        if price and price > 0:
            logger.info("Yahoo Finance %s: $%.2f", symbol, price)
            return round(price, 2)
    except Exception as e:
        logger.warning("Yahoo Finance %s fetch failed: %s", symbol, e)
    return None


def refresh_us_stock_prices(group=None):
    """
    Refresh current prices for all US stock (RSU) holdings.
    Fetches latest stock price + USD/INR rate and updates each holding.
    Returns dict with results or None on failure.
    """
    holdings = USStockHolding.objects.all()
    if group is not None:
        holdings = holdings.filter(group=group)
    if not holdings.exists():
        return None

    usd_inr = _fetch_usd_inr_rate()
    if not usd_inr:
        logger.warning("Could not fetch USD/INR rate for US stock refresh")
        return None

    symbols = set(holdings.values_list('symbol', flat=True))
    prices = {}
    for sym in symbols:
        price = _fetch_stock_price_usd(sym)
        if price:
            prices[sym] = price

    if not prices:
        logger.warning("Could not fetch any US stock prices")
        return None

    now = timezone.now()
    usd_inr_dec = Decimal(str(usd_inr))
    to_update = []
    for h in holdings:
        if h.symbol in prices:
            h.current_price_usd = Decimal(str(prices[h.symbol]))
            h.current_usd_inr = usd_inr_dec
            h.last_refreshed = now
            to_update.append(h)

    if to_update:
        USStockHolding.objects.bulk_update(
            to_update, ['current_price_usd', 'current_usd_inr', 'last_refreshed'],
        )

    results = {
        'usd_inr': usd_inr,
        'updated': len(to_update),
        'prices': prices,
    }
    logger.info("US stock refresh: %s", results)
    return results


def fetch_and_fill_us_stock_prices(holding):
    """
    Auto-fill purchase and current prices for a newly added US stock holding.
    Called when saving a new holding with purchase_price_usd == 0.
    """
    price = _fetch_stock_price_usd(holding.symbol)
    usd_inr = _fetch_usd_inr_rate()

    if price and usd_inr:
        usd_inr_dec = Decimal(str(usd_inr))
        price_dec = Decimal(str(price))

        if not holding.purchase_price_usd:
            holding.purchase_price_usd = price_dec
        if not holding.purchase_usd_inr:
            holding.purchase_usd_inr = usd_inr_dec

        holding.current_price_usd = price_dec
        holding.current_usd_inr = usd_inr_dec
        holding.last_refreshed = timezone.now()


# ---------------------------------------------------------------------------
# FY-end land appreciation
# ---------------------------------------------------------------------------

LAND_PROPERTY_TYPES = ('PLOT_LAND', 'AGRICULTURAL')
_MANUAL_REVALUATION_GRACE_DAYS = 30


def apply_annual_land_appreciation(pct=Decimal('6'), today=None, group=None, dry_run=False):
    """Mark land up by ``pct`` once for the FY that just closed (meant to run on 1 April).

    Idempotent via ``last_appreciated_fy``. Plots revalued by hand in the last 30 days are
    treated as already reflecting the year-end price and are only marked as done.
    """
    today = today or datetime.date.today()
    closing_fy = fy_label(fy_start_year(today) - 1)
    factor = 1 + Decimal(str(pct)) / 100

    qs = RealEstateHolding.objects.filter(property_type__in=LAND_PROPERTY_TYPES)
    if group is not None:
        qs = qs.filter(group=group)

    results = []
    for h in qs.exclude(last_appreciated_fy=closing_fy):
        old = h.current_valuation
        recent_manual = (
            h.last_valuation_date is not None
            and (today - h.last_valuation_date).days < _MANUAL_REVALUATION_GRACE_DAYS
        )
        new = old if recent_manual else (old * factor).quantize(Decimal('1'))
        results.append({'holding': h, 'old': old, 'new': new, 'skipped': recent_manual})
        if dry_run:
            continue
        h.last_appreciated_fy = closing_fy
        fields = ['last_appreciated_fy', 'updated_at']
        if not recent_manual:
            h.current_valuation = new
            h.last_valuation_date = today
            fields += ['current_valuation', 'last_valuation_date']
        h.save(update_fields=fields)
    return closing_fy, results


# ---------------------------------------------------------------------------
# Monthly snapshots
# ---------------------------------------------------------------------------

def take_monthly_snapshot(month=None, group=None):
    """
    Capture the current portfolio state as a MonthlySnapshot, scoped to group.
    `month` should be a date representing the first of the month.
    If None, uses current month.
    If group is None, snapshots all groups that have portfolio data.
    """
    from tracker.models import AccountGroup

    if month is None:
        month = datetime.date.today().replace(day=1)

    if group is not None:
        return _take_snapshot_for_group(month, group)

    # Snapshot every group that has at least one portfolio model row.
    groups = AccountGroup.objects.all()
    last_result = None
    for g in groups:
        last_result = _take_snapshot_for_group(month, g)
    return last_result


def _take_snapshot_for_group(month, group):
    summary = get_portfolio_summary(group)

    data = {}
    for asset in summary['assets']:
        key = asset['name'].lower().replace(' ', '_')
        data[key] = {
            'current': float(asset['value']),
            'pct': float(asset['pct']),
        }

    data['epf'] = {
        'invested': float(summary['epf_total_contrib']),
        'current': float(summary['epf_balance']),
        'interest': float(summary['epf_total_interest']),
    }
    data.setdefault('index_funds', {})['invested'] = float(
        _sum_qs(MutualFundHolding.objects.filter(account__group=group, fund_type='INDEX'), 'purchase_value'))
    data.setdefault('individual_stocks', {})['invested'] = float(
        _sum_qs(StockHolding.objects.filter(account__group=group), 'purchase_value'))
    data.setdefault('other_mutual_funds', {})['invested'] = float(
        _sum_qs(MutualFundHolding.objects.filter(account__group=group, fund_type='OTHER'), 'purchase_value'))
    data.setdefault('crypto', {})['invested'] = float(summary['crypto_invested'])
    data.setdefault('fd', {})['principal'] = float(summary['fd_principal'])
    data.setdefault('us_stocks', {})['invested'] = float(summary['us_stocks_invested'])
    data.setdefault('real_estate', {})['invested'] = float(summary['real_estate_invested'])

    total_invested = summary['total_invested']
    total_current = summary['total_value']
    total_returns = total_current - total_invested

    prev = MonthlySnapshot.objects.filter(group=group, month__lt=month).order_by('-month').first()
    if prev:
        money_added = total_invested - prev.total_invested
        returns_change = total_returns - prev.total_returns
    else:
        money_added = total_invested
        returns_change = total_returns

    snapshot, created = MonthlySnapshot.objects.update_or_create(
        group=group, month=month,
        defaults={
            'data': data,
            'total_invested': total_invested,
            'total_current_value': total_current,
            'total_returns': total_returns,
            'money_added_this_month': money_added,
            'returns_this_month': returns_change,
        },
    )
    if month.month == 3:
        FinancialGoal.objects.filter(
            group=group, financial_year=fy_label(month.year - 1),
        ).update(closing_value=total_current.quantize(Decimal('1')))
    return snapshot, created


# ---------------------------------------------------------------------------
# Growth data
# ---------------------------------------------------------------------------

def get_growth_data(fy_year=None, group=None):
    """
    Return monthly snapshots for a financial year, scoped to group.
    FY runs April to March: fy_year=2025 means Apr 2025 → Mar 2026.
    """
    if fy_year is None:
        fy_year = fy_start_year(datetime.date.today())

    all_snaps = list(_gf(MonthlySnapshot.objects, group).order_by('month'))

    snap_by_month = {s.month: s for s in all_snaps}
    snaps_by_fy = {}
    for s in all_snaps:
        snaps_by_fy.setdefault(fy_start_year(s.month), []).append(s)

    available_fys = set(snaps_by_fy.keys()) or {fy_year}

    fy_month_names = [
        'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
        'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar',
    ]
    months = []
    for i, name in enumerate(fy_month_names):
        m = i + 4 if i < 9 else i - 8
        y = fy_year if m >= 4 else fy_year + 1
        month_date = datetime.date(y, m, 1)
        snap = snap_by_month.get(month_date)
        months.append({
            'name': name,
            'date': month_date,
            'snapshot': snap,
            'total_value': float(snap.total_current_value) if snap else 0,
            'invested': float(snap.total_invested) if snap else 0,
            'returns': float(snap.total_returns) if snap else 0,
            'money_added': float(snap.money_added_this_month) if snap else 0,
            'returns_gained': float(snap.returns_this_month) if snap else 0,
        })

    yearly = []
    prev_fy_last = None
    for fy in sorted(available_fys):
        fy_snaps = snaps_by_fy.get(fy, [])
        if not fy_snaps:
            continue
        last = fy_snaps[-1]
        yearly.append({
            'label': fy_label(fy),
            'fy': fy,
            'total_value': float(last.total_current_value),
            'invested': float(last.total_invested),
            'returns': float(last.total_returns),
            'money_added': sum(float(s.money_added_this_month) for s in fy_snaps),
            'returns_gained': sum(float(s.returns_this_month) for s in fy_snaps),
            'start_value': float(prev_fy_last.total_current_value) if prev_fy_last else 0,
            'has_data': True,
        })
        prev_fy_last = last

    return {
        'fy_year': fy_year,
        'fy_label': fy_label(fy_year),
        'months': months,
        'yearly': yearly,
        'fy_options': sorted(available_fys),
    }
