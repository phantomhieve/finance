import inspect
import json
import time
import datetime
import logging
from collections import OrderedDict
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from tracker.models import WebAuthnCredential

from pftracker.utils import ZERO as _ZERO, safe_redirect, pnl_pct as _pnl_pct

from .models import (
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit,
    CashPosition, BondHolding, CryptoHolding,
    CommodityHolding, USStockHolding,
    MonthlySnapshot, FinancialGoal,
    PortfolioInsight,
    InsightGenerationSettings,
)
from .forms import (
    EPFEntryForm, NPSEntryForm, FixedDepositForm,
    CashPositionForm, BondHoldingForm, CryptoHoldingForm,
    CommodityHoldingForm, FinancialGoalForm, USStockHoldingForm,
)
from tracker.services import parse_fy_param
from .services import (
    get_portfolio_summary,
    get_commodity_summary,
    sync_zerodha_from_sheets,
    refresh_commodity_prices,
    refresh_us_stock_prices,
    fetch_and_fill_us_stock_prices,
    get_growth_data,
    take_monthly_snapshot,
)
from .ai import build_prompt_data, call_gemini

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PORTFOLIO_UNLOCK_TTL = 300  # 5 minutes

def _require_portfolio(view_func):
    """Only PRIMARY users can access portfolio views; always gate behind group password."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.can_view_portfolio:
            return HttpResponseForbidden('You do not have permission to view this page.')
        unlocked_at = request.session.get('portfolio_unlocked_at')
        if not unlocked_at or (time.time() - unlocked_at) > _PORTFOLIO_UNLOCK_TTL:
            request.session.pop('portfolio_unlocked_at', None)
            return redirect('/portfolio/unlock/?next=' + quote(request.get_full_path()))
        request.portfolio_expires_at = int(unlocked_at + _PORTFOLIO_UNLOCK_TTL)
        return view_func(request, *args, **kwargs)
    return _wrapped


_UNLOCK_ATTEMPT_KEY = '_portfolio_unlock_attempts'
_UNLOCK_LOCKOUT_KEY = '_portfolio_unlock_lockout'
_MAX_UNLOCK_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300


@login_required
def portfolio_unlock(request):
    next_url = request.GET.get('next', request.POST.get('next', '/portfolio/'))
    allowed = url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
    if not allowed:
        next_url = '/portfolio/'

    lockout_until = request.session.get(_UNLOCK_LOCKOUT_KEY, 0)
    if lockout_until and time.time() < lockout_until:
        remaining = int(lockout_until - time.time())
        messages.error(request, f'Too many failed attempts. Try again in {remaining // 60}m {remaining % 60}s.')
        return render(request, 'portfolio/unlock.html', {
            'next': next_url, 'has_password': True, 'has_webauthn': False,
        })

    group = request.user.group
    has_password = bool(group and group.portfolio_password)
    if request.method == 'POST' and has_password:
        password = request.POST.get('password', '')
        if group.check_portfolio_password(password):
            request.session.pop(_UNLOCK_ATTEMPT_KEY, None)
            request.session.pop(_UNLOCK_LOCKOUT_KEY, None)
            request.session['portfolio_unlocked_at'] = time.time()
            return redirect(next_url)
        attempts = request.session.get(_UNLOCK_ATTEMPT_KEY, 0) + 1
        request.session[_UNLOCK_ATTEMPT_KEY] = attempts
        if attempts >= _MAX_UNLOCK_ATTEMPTS:
            request.session[_UNLOCK_LOCKOUT_KEY] = time.time() + _LOCKOUT_SECONDS
            request.session[_UNLOCK_ATTEMPT_KEY] = 0
            messages.error(request, f'Too many failed attempts. Locked for {_LOCKOUT_SECONDS // 60} minutes.')
        else:
            messages.error(request, 'Incorrect portfolio password.')
    has_webauthn = WebAuthnCredential.objects.filter(user=request.user).exists()
    return render(request, 'portfolio/unlock.html', {
        'next': next_url,
        'has_password': has_password,
        'has_webauthn': has_webauthn,
    })


def _user_group(request):
    return request.user.group


def _safe_redirect(request, fallback='portfolio_tracker'):
    return safe_redirect(request, fallback)


def _auto_snapshot(group):
    """
    Silently create a snapshot for the previous month if one doesn't exist.
    Only triggers when at least one older snapshot already exists, so the
    very first month of tracking doesn't produce a phantom prior-month entry.
    """
    today = datetime.date.today()
    if today.day <= 1:
        return
    prev_month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    if MonthlySnapshot.objects.filter(group=group, month=prev_month).exists():
        return
    if not MonthlySnapshot.objects.filter(group=group, month__lt=prev_month).exists():
        return
    try:
        take_monthly_snapshot(month=prev_month, group=group)
        logger.info("Auto-created snapshot for %s (group %s)", prev_month.strftime('%b %Y'), group)
    except Exception as e:
        logger.warning("Auto-snapshot failed: %s", e)


def _holding_totals(items, purchase_attr='purchase_value',
                    current_attr='current_value'):
    purchased = sum(getattr(h, purchase_attr) for h in items)
    current = sum(getattr(h, current_attr) for h in items)
    pnl = current - purchased
    return purchased, current, pnl


# ---------------------------------------------------------------------------
# Generic CRUD factory
# ---------------------------------------------------------------------------

def _make_crud_views(model_class, form_class, label):
    """
    Generate add / edit / delete views for a model + form pair.
    Returns (add_view, edit_view, delete_view) tuple.
    """

    _form_accepts_group = 'group' in inspect.signature(form_class.__init__).parameters

    def _build_form(request, *args, **kwargs):
        if _form_accepts_group:
            kwargs['group'] = _user_group(request)
        return form_class(*args, **kwargs)

    @login_required
    @_require_portfolio
    @require_POST
    def add_view(request):
        form = _build_form(request, request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if hasattr(obj, 'group'):
                obj.group = _user_group(request)
            obj.save()
            messages.success(request, f'{label} added.')
        else:
            logger.warning("Invalid %s form: %s", label, form.errors.as_text())
            messages.error(request, f'Invalid {label.lower()} entry.')
        return _safe_redirect(request)

    @login_required
    @_require_portfolio
    @require_POST
    def edit_view(request, pk):
        lookup = {'pk': pk}
        if hasattr(model_class, 'group'):
            lookup['group'] = _user_group(request)
        obj = get_object_or_404(model_class, **lookup)
        form = _build_form(request, request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'{label} updated.')
        else:
            logger.warning("Invalid %s edit form (pk=%s): %s", label, pk, form.errors.as_text())
            messages.error(request, f'Invalid {label.lower()} entry.')
        return _safe_redirect(request)

    @login_required
    @_require_portfolio
    @require_POST
    def delete_view(request, pk):
        lookup = {'pk': pk}
        if hasattr(model_class, 'group'):
            lookup['group'] = _user_group(request)
        get_object_or_404(model_class, **lookup).delete()
        messages.success(request, f'{label} deleted.')
        return _safe_redirect(request)

    add_view.__name__ = f'add_{model_class.__name__.lower()}'
    edit_view.__name__ = f'edit_{model_class.__name__.lower()}'
    delete_view.__name__ = f'delete_{model_class.__name__.lower()}'

    return add_view, edit_view, delete_view


add_epf_entry, edit_epf_entry, delete_epf_entry = _make_crud_views(
    EPFEntry, EPFEntryForm, 'EPF entry')

add_nps_entry, edit_nps_entry, delete_nps_entry = _make_crud_views(
    NPSEntry, NPSEntryForm, 'NPS entry')

add_fd, edit_fd, delete_fd = _make_crud_views(
    FixedDeposit, FixedDepositForm, 'Fixed deposit')

add_cash, edit_cash, delete_cash = _make_crud_views(
    CashPosition, CashPositionForm, 'Cash position')

add_bond, edit_bond, delete_bond = _make_crud_views(
    BondHolding, BondHoldingForm, 'Bond holding')

add_crypto, edit_crypto, delete_crypto = _make_crud_views(
    CryptoHolding, CryptoHoldingForm, 'Crypto holding')

add_commodity, edit_commodity, delete_commodity = _make_crud_views(
    CommodityHolding, CommodityHoldingForm, 'Commodity holding')

add_goal, edit_goal, delete_goal = _make_crud_views(
    FinancialGoal, FinancialGoalForm, 'Financial goal')


@login_required
@_require_portfolio
@require_POST
def add_us_stock(request):
    form = USStockHoldingForm(request.POST)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.group = _user_group(request)
        fetch_and_fill_us_stock_prices(obj)
        obj.save()
        messages.success(request, f'{obj.symbol} RSU holding added — {obj.quantity} shares.')
    else:
        logger.warning("Invalid US stock form: %s", form.errors.as_text())
        messages.error(request, 'Invalid US stock entry.')
    return _safe_redirect(request)


@login_required
@_require_portfolio
@require_POST
def edit_us_stock(request, pk):
    obj = get_object_or_404(USStockHolding, pk=pk, group=_user_group(request))
    form = USStockHoldingForm(request.POST, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'US stock holding updated.')
    else:
        logger.warning("Invalid US stock edit form (pk=%s): %s", pk, form.errors.as_text())
        messages.error(request, 'Invalid US stock entry.')
    return _safe_redirect(request)


@login_required
@_require_portfolio
@require_POST
def delete_us_stock(request, pk):
    get_object_or_404(USStockHolding, pk=pk, group=_user_group(request)).delete()
    messages.success(request, 'US stock holding deleted.')
    return _safe_redirect(request)


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

def _insight_cooldown_timedelta():
    """Production uses DB-backed cooldown; DEBUG disables cooldown."""
    if settings.DEBUG:
        return datetime.timedelta(0)
    days = InsightGenerationSettings.get_solo().cooldown_days
    days = max(0, min(int(days), 366))
    return datetime.timedelta(days=days)


def _insight_cooldown_hint():
    if settings.DEBUG:
        return None
    return InsightGenerationSettings.get_solo().cooldown_days


def _insight_can_generate(group):
    """Check if enough time has passed since the last AI insight generation."""
    from django.utils import timezone as _tz
    qs = PortfolioInsight.objects.filter(group=group).order_by('-generated_at')
    latest = qs.first()
    if not latest:
        return latest, True
    cooldown = _insight_cooldown_timedelta()
    can = (_tz.now() - latest.generated_at) >= cooldown
    return latest, can


@login_required
@_require_portfolio
def master_portfolio(request):
    group = _user_group(request)
    _auto_snapshot(group)
    summary = get_portfolio_summary(group)
    latest_insight, can_generate = _insight_can_generate(group)
    if latest_insight and latest_insight.insights.get('insights'):
        sev_order = {'critical': 0, 'warning': 1, 'info': 2, 'positive': 3}
        latest_insight.insights['insights'].sort(
            key=lambda i: sev_order.get(i.get('severity', ''), 9)
        )
    pf_chart_data = {
        'labels': [a['name'] for a in summary['assets']],
        'values': [float(a['value']) for a in summary['assets']],
        'consolidated_labels': [c['name'] for c in summary['consolidated']],
        'consolidated_values': [float(c['value']) for c in summary['consolidated']],
    }
    ctx = {
        **summary,
        'latest_insight': latest_insight,
        'can_generate_insight': can_generate,
        'insight_cooldown_days_hint': _insight_cooldown_hint(),
        'epf_form': EPFEntryForm(),
        'nps_form': NPSEntryForm(group=group),
        'fd_form': FixedDepositForm(),
        'cash_form': CashPositionForm(),
        'bond_form': BondHoldingForm(),
        'crypto_form': CryptoHoldingForm(),
        'commodity_form': CommodityHoldingForm(),
        'us_stock_form': USStockHoldingForm(),
        'goal_form': FinancialGoalForm(),
        'pf_chart_data': pf_chart_data,
        'webauthn_credentials': WebAuthnCredential.objects.filter(user=request.user),
    }
    return render(request, 'portfolio/master.html', ctx)


@login_required
@_require_portfolio
def zerodha_detail(request, slug):
    account = get_object_or_404(ZerodhaAccount, slug=slug, group=_user_group(request))
    stocks = list(account.stock_holdings.all())
    index_mf = list(account.mf_holdings.filter(fund_type='INDEX'))
    other_mf = list(account.mf_holdings.filter(fund_type='OTHER'))

    s_purch, s_curr, s_pnl = _holding_totals(stocks)
    i_purch, i_curr, i_pnl = _holding_totals(index_mf)
    o_purch, o_curr, o_pnl = _holding_totals(other_mf)

    total_invested = s_purch + i_purch + o_purch
    total_returns = (s_curr + i_curr + o_curr) - total_invested

    ctx = {
        'account': account,
        'stocks': stocks,
        'index_mf': index_mf,
        'other_mf': other_mf,
        'total_stocks': s_curr,
        'total_stocks_purchased': s_purch,
        'total_stocks_pnl': s_pnl,
        'total_index': i_curr,
        'total_index_purchased': i_purch,
        'total_index_pnl': i_pnl,
        'total_other': o_curr,
        'total_other_purchased': o_purch,
        'total_other_pnl': o_pnl,
        'total_portfolio': s_curr + i_curr + o_curr,
        'total_invested': total_invested,
        'total_returns': total_returns,
    }
    return render(request, 'portfolio/zerodha_detail.html', ctx)


def _merge_holdings(items, key_fn):
    merged = OrderedDict()
    for item in items:
        k = key_fn(item)
        if k not in merged:
            merged[k] = {
                'name': k, 'quantity': 0,
                'purchase_value': _ZERO, 'current_value': _ZERO,
                'units': _ZERO, 'entries': [],
            }
        g = merged[k]
        g['quantity'] += getattr(item, 'quantity', 0)
        g['units'] += getattr(item, 'units', _ZERO)
        g['purchase_value'] += item.purchase_value
        g['current_value'] += item.current_value
        g['entries'].append({
            'account': item.account.name,
            'quantity': getattr(item, 'quantity', 0),
            'units': str(getattr(item, 'units', _ZERO)),
            'purchase_value': str(item.purchase_value),
            'current_value': str(item.current_value),
            'pnl': str(item.current_value - item.purchase_value),
        })

    result = []
    for g in merged.values():
        g['pnl'] = g['current_value'] - g['purchase_value']
        g['pnl_pct'] = _pnl_pct(g['pnl'], g['purchase_value'])
        g['multi'] = len(g['entries']) > 1
        g['entries_json'] = json.dumps(g['entries']).replace('</', r'<\/')
        result.append(g)
    result.sort(key=lambda x: x['current_value'], reverse=True)
    return result


@login_required
@_require_portfolio
def zerodha_consolidated(request):
    group = _user_group(request)
    group_accounts = ZerodhaAccount.objects.filter(group=group)
    acct_ids = group_accounts.values_list('id', flat=True)

    all_stocks = list(StockHolding.objects.select_related('account').filter(account_id__in=acct_ids))
    all_index = list(MutualFundHolding.objects.select_related('account').filter(account_id__in=acct_ids, fund_type='INDEX'))
    all_other = list(MutualFundHolding.objects.select_related('account').filter(account_id__in=acct_ids, fund_type='OTHER'))
    accounts = list(group_accounts)

    stocks = _merge_holdings(all_stocks, lambda s: s.symbol)
    index_mf = _merge_holdings(all_index, lambda m: m.fund_name)
    other_mf = _merge_holdings(all_other, lambda m: m.fund_name)

    s_purch, s_curr, s_pnl = _holding_totals(all_stocks)
    i_purch, i_curr, i_pnl = _holding_totals(all_index)
    o_purch, o_curr, o_pnl = _holding_totals(all_other)

    total_portfolio = s_curr + i_curr + o_curr
    total_purchased = s_purch + i_purch + o_purch
    total_pnl = s_pnl + i_pnl + o_pnl

    all_merged = stocks + index_mf + other_mf
    top_gainers = sorted(
        [h for h in all_merged if h['pnl'] > 0],
        key=lambda x: x['pnl'], reverse=True,
    )[:5]
    top_losers = sorted(
        [h for h in all_merged if h['pnl'] < 0],
        key=lambda x: x['pnl'],
    )[:5]

    per_acct = {}
    for h in all_stocks + all_index + all_other:
        rec = per_acct.setdefault(h.account_id, {'invested': _ZERO, 'current': _ZERO, 'count': 0})
        rec['invested'] += h.purchase_value
        rec['current'] += h.current_value
        rec['count'] += 1

    acct_stats = []
    for acct in accounts:
        rec = per_acct.get(acct.id, {'invested': _ZERO, 'current': _ZERO, 'count': 0})
        a_pnl = rec['current'] - rec['invested']
        acct_stats.append({
            'name': acct.name,
            'slug': acct.slug,
            'invested': rec['invested'],
            'current': rec['current'],
            'pnl': a_pnl,
            'pnl_pct': _pnl_pct(a_pnl, rec['invested']),
            'holdings': rec['count'],
        })

    consolidated_data = {
        'stock': [{'name': s['name'], 'entries': s['entries']} for s in stocks],
        'index': [{'name': m['name'], 'entries': m['entries']} for m in index_mf],
        'other': [{'name': m['name'], 'entries': m['entries']} for m in other_mf],
    }
    equity_chart_data = {
        'labels': ['Stocks', 'Index Funds', 'Other MF'],
        'values': [float(s_curr), float(i_curr), float(o_curr)],
    }

    ctx = {
        'accounts': accounts,
        'acct_stats': acct_stats,
        'stocks': stocks,
        'index_mf': index_mf,
        'other_mf': other_mf,
        'total_stocks': s_curr,
        'total_stocks_purchased': s_purch,
        'total_stocks_pnl': s_pnl,
        'total_index': i_curr,
        'total_index_purchased': i_purch,
        'total_index_pnl': i_pnl,
        'total_other': o_curr,
        'total_other_purchased': o_purch,
        'total_other_pnl': o_pnl,
        'total_portfolio': total_portfolio,
        'total_purchased': total_purchased,
        'total_pnl': total_pnl,
        'total_pnl_pct': _pnl_pct(total_pnl, total_purchased),
        'top_gainers': top_gainers,
        'top_losers': top_losers,
        'holding_count': len(all_merged),
        'consolidated_data': consolidated_data,
        'equity_chart_data': equity_chart_data,
    }
    return render(request, 'portfolio/zerodha_consolidated.html', ctx)


# ---------------------------------------------------------------------------
# Section detail views ("View All" pages)
# ---------------------------------------------------------------------------

@login_required
@_require_portfolio
def epf_detail(request):
    group = _user_group(request)
    entries = list(EPFEntry.objects.filter(group=group))
    contrib = sum((e.amount for e in entries if e.entry_type == 'CONTRIBUTION'), _ZERO)
    interest = sum((e.amount for e in entries if e.entry_type == 'INTEREST'), _ZERO)
    return render(request, 'portfolio/epf_detail.html', {
        'entries': entries, 'total_contrib': contrib,
        'total_interest': interest, 'balance': contrib + interest,
        'form': EPFEntryForm(),
    })


@login_required
@_require_portfolio
def nps_detail(request):
    group = _user_group(request)
    entries = list(NPSEntry.objects.filter(group=group))
    latest = entries[0] if entries else None
    return render(request, 'portfolio/nps_detail.html', {
        'entries': entries, 'latest': latest,
        'balance': latest.total_balance if latest else _ZERO,
        'form': NPSEntryForm(group=group),
    })


@login_required
@_require_portfolio
def fd_detail(request):
    group = _user_group(request)
    active_fds = list(FixedDeposit.objects.filter(group=group, is_active=True))
    matured_fds = list(FixedDeposit.objects.filter(group=group, is_active=False))
    active_total = sum((fd.current_value for fd in active_fds), _ZERO)
    matured_total = sum((fd.maturity_value for fd in matured_fds), _ZERO)
    total_interest = (
        sum((fd.current_value - fd.principal for fd in active_fds), _ZERO)
        + sum((fd.maturity_value - fd.principal for fd in matured_fds), _ZERO)
    )
    return render(request, 'portfolio/fd_detail.html', {
        'active_fds': active_fds,
        'matured_fds': matured_fds,
        'active_total': active_total,
        'matured_total': matured_total,
        'total_interest': total_interest,
        'form': FixedDepositForm(),
    })


@login_required
@_require_portfolio
def cash_detail(request):
    group = _user_group(request)
    positions = list(CashPosition.objects.filter(group=group))
    return render(request, 'portfolio/cash_detail.html', {
        'positions': positions,
        'total': sum((c.amount for c in positions), _ZERO),
        'form': CashPositionForm(),
    })


@login_required
@_require_portfolio
def bonds_detail(request):
    group = _user_group(request)
    bonds = list(BondHolding.objects.filter(group=group))
    return render(request, 'portfolio/bonds_detail.html', {
        'bonds': bonds,
        'total': sum((b.amount for b in bonds), _ZERO),
        'form': BondHoldingForm(),
    })


@login_required
@_require_portfolio
def crypto_detail(request):
    group = _user_group(request)
    holdings = list(CryptoHolding.objects.filter(group=group))
    total_invested = sum((h.amount_invested for h in holdings), _ZERO)
    total_current = sum((h.current_value for h in holdings), _ZERO)
    return render(request, 'portfolio/crypto_detail.html', {
        'holdings': holdings,
        'total_invested': total_invested,
        'total_current': total_current,
        'total_pnl': total_current - total_invested,
        'form': CryptoHoldingForm(),
    })


@login_required
@_require_portfolio
def commodities_detail(request):
    group = _user_group(request)
    comm = get_commodity_summary(group)
    rates = {'GOLD': comm['gold_rate'], 'SILVER': comm['silver_rate']}

    holdings = list(CommodityHolding.objects.filter(group=group))
    for h in holdings:
        h._cached_rate = rates.get(h.commodity_type, _ZERO)
    gold_holdings = [h for h in holdings if h.commodity_type == 'GOLD']
    silver_holdings = [h for h in holdings if h.commodity_type == 'SILVER']

    return render(request, 'portfolio/commodities_detail.html', {
        'gold_holdings': gold_holdings,
        'silver_holdings': silver_holdings,
        'gold_rate': comm['gold_rate'],
        'silver_rate': comm['silver_rate'],
        'gold_weight': comm['gold_weight'],
        'silver_weight': comm['silver_weight'],
        'gold_value': comm['gold_value'],
        'silver_value': comm['silver_value'],
        'gold_price_obj': comm['gold_price_obj'],
        'silver_price_obj': comm['silver_price_obj'],
        'total': comm['commodity_total'],
        'total_invested': comm['commodity_invested'],
        'total_returns': comm['commodity_returns'],
        'form': CommodityHoldingForm(),
    })


@login_required
@_require_portfolio
def portfolio_growth(request):
    group = _user_group(request)
    fy_year = parse_fy_param(request.GET.get('fy'), None)
    growth = get_growth_data(fy_year, group=group)
    growth['growth_chart_data'] = {
        'months': [m['name'] for m in growth['months']],
        'values': [m['total_value'] for m in growth['months']],
        'money_added': [m['money_added'] for m in growth['months']],
        'returns_gained': [m['returns_gained'] for m in growth['months']],
        'yearly_labels': [y['label'] for y in growth['yearly']],
        'yearly_values': [y['total_value'] for y in growth['yearly']],
        'yearly_added': [y['money_added'] for y in growth['yearly']],
        'yearly_returns': [y['returns_gained'] for y in growth['yearly']],
    }
    return render(request, 'portfolio/growth.html', growth)


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------

@login_required
@_require_portfolio
@require_POST
def sync_from_sheets(request):
    group = _user_group(request)
    try:
        results = sync_zerodha_from_sheets(group=group)
        for r in results:
            if 'error' in r:
                messages.error(request, f"Sync failed for {r['account']}. Please check your sheet configuration.")
            else:
                messages.success(
                    request,
                    f"Synced {r['account']}: {r['stocks']} stocks, "
                    f"{r['index_mf']} index MFs, {r['other_mf']} other MFs",
                )
    except Exception:
        logger.exception("Sheets sync error")
        messages.error(request, "Sheets sync failed. Please try again later.")
    return _safe_redirect(request)


@login_required
@_require_portfolio
@require_POST
def refresh_prices(request):
    try:
        results = refresh_commodity_prices()
        if results:
            parts = []
            if 'gold' in results:
                parts.append(f"Gold: \u20b9{results['gold']:,.2f}/g")
            if 'silver' in results:
                parts.append(f"Silver: \u20b9{results['silver']:,.2f}/g")
            messages.success(request, f"Prices updated \u2014 {', '.join(parts)}")
        else:
            messages.warning(request, "Could not fetch commodity prices. Check API key or try again later.")
    except Exception:
        logger.exception("Commodity price refresh error")
        messages.error(request, "Commodity price refresh failed.")

    try:
        group = _user_group(request)
        us_results = refresh_us_stock_prices(group=group)
        if us_results:
            stock_parts = []
            for sym, price in us_results['prices'].items():
                stock_parts.append(f"{sym}: ${price:.2f}")
            rate_str = f"USD/INR: \u20b9{us_results['usd_inr']:,.2f}"
            messages.success(
                request,
                f"US stocks updated \u2014 {', '.join(stock_parts)} ({rate_str})"
            )
    except Exception:
        logger.exception("US stock price refresh error")
        messages.error(request, "US stock price refresh failed.")

    return _safe_redirect(request)


@login_required
@_require_portfolio
@require_POST
def take_snapshot_view(request):
    group = _user_group(request)
    try:
        snapshot, created = take_monthly_snapshot(group=group)
        verb = "Created" if created else "Updated"
        messages.success(request, f"{verb} snapshot for {snapshot.month:%b %Y}")
    except Exception:
        logger.exception("Snapshot error")
        messages.error(request, "Snapshot failed. Please try again later.")
    return _safe_redirect(request)


@login_required
@_require_portfolio
@require_POST
def generate_insights(request):
    group = _user_group(request)
    from django.utils import timezone as _tz
    last, can = _insight_can_generate(group)
    if last and not can:
        remaining = cooldown_td - (_tz.now() - last.generated_at)
        secs = max(0, int(remaining.total_seconds()))
        days = secs // 86400
        hours = (secs % 86400) // 3600
        cfg_days = InsightGenerationSettings.get_solo().cooldown_days
        messages.warning(
            request,
            f"AI insights cooldown is {cfg_days} day(s). Try again in {days}d {hours}h.",
        )
        return redirect('portfolio_tracker')
    try:
        summary = get_portfolio_summary(group)
        growth = get_growth_data(group=group)
        prompt_data = build_prompt_data(summary, growth, group)
        result = call_gemini(prompt_data)
        PortfolioInsight.objects.create(
            group=group,
            model_used=result.model,
            prompt_data=prompt_data,
            insights=result.insights_dict,
        )
        messages.success(request, "AI portfolio analysis generated successfully.")
    except Exception:
        logger.exception("AI insights generation error")
        messages.error(request, "Failed to generate AI insights. Please try again later.")
    return redirect('portfolio_tracker')


# ---------------------------------------------------------------------------
# WebAuthn (FaceID / biometric) endpoints
# ---------------------------------------------------------------------------

_MAX_WEBAUTHN_CREDENTIALS = 5


@login_required
@require_POST
def webauthn_register_begin(request):
    """Start biometric registration. Requires portfolio already unlocked."""
    if not request.user.can_view_portfolio:
        return JsonResponse({'error': 'Forbidden.'}, status=403)
    unlocked_at = request.session.get('portfolio_unlocked_at')
    if not unlocked_at or (time.time() - unlocked_at) > _PORTFOLIO_UNLOCK_TTL:
        return JsonResponse({'error': 'Portfolio must be unlocked first.'}, status=403)

    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    user = request.user
    existing = WebAuthnCredential.objects.filter(user=user)
    if existing.count() >= _MAX_WEBAUTHN_CREDENTIALS:
        return JsonResponse({'error': f'Maximum {_MAX_WEBAUTHN_CREDENTIALS} devices allowed.'}, status=400)

    exclude_creds = [
        PublicKeyCredentialDescriptor(id=bytes(c.credential_id))
        for c in existing
    ]

    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(user.pk).encode(),
        user_name=user.username,
        user_display_name=user.get_full_name() or user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude_creds,
    )

    request.session['webauthn_reg_challenge'] = options.challenge.hex()
    return JsonResponse(json.loads(options_to_json(options)))


@login_required
@require_POST
def webauthn_register_complete(request):
    """Complete biometric registration and store the credential."""
    if not request.user.can_view_portfolio:
        return JsonResponse({'error': 'Forbidden.'}, status=403)
    challenge_hex = request.session.pop('webauthn_reg_challenge', None)
    if not challenge_hex:
        return JsonResponse({'error': 'No registration in progress.'}, status=400)

    from webauthn import verify_registration_response

    try:
        body = json.loads(request.body)
        verification = verify_registration_response(
            credential=body,
            expected_challenge=bytes.fromhex(challenge_hex),
            expected_origin=settings.WEBAUTHN_ORIGIN,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            require_user_verification=True,
        )
    except Exception:
        logger.exception("WebAuthn registration verification failed")
        return JsonResponse({'error': 'Registration verification failed.'}, status=400)

    device_name = str(body.get('device_name', 'Device'))[:100]
    WebAuthnCredential.objects.create(
        user=request.user,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_name=device_name,
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def webauthn_auth_begin(request):
    """Start biometric authentication on the unlock page."""
    if not request.user.can_view_portfolio:
        return JsonResponse({'error': 'Forbidden.'}, status=403)

    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    creds = WebAuthnCredential.objects.filter(user=request.user)
    if not creds.exists():
        return JsonResponse({'error': 'No biometric credentials registered.'}, status=404)

    allow_creds = [
        PublicKeyCredentialDescriptor(id=bytes(c.credential_id))
        for c in creds
    ]

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow_creds,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    request.session['webauthn_auth_challenge'] = options.challenge.hex()
    return JsonResponse(json.loads(options_to_json(options)))


@login_required
@require_POST
def webauthn_auth_complete(request):
    """Verify biometric authentication and unlock the portfolio."""
    if not request.user.can_view_portfolio:
        return JsonResponse({'error': 'Forbidden.'}, status=403)
    challenge_hex = request.session.pop('webauthn_auth_challenge', None)
    if not challenge_hex:
        return JsonResponse({'error': 'No authentication in progress.'}, status=400)

    from webauthn import verify_authentication_response, base64url_to_bytes

    try:
        body = json.loads(request.body)
        raw_id = base64url_to_bytes(body['rawId'])
        cred = WebAuthnCredential.objects.get(credential_id=raw_id, user=request.user)
    except (WebAuthnCredential.DoesNotExist, KeyError):
        return JsonResponse({'error': 'Authentication failed.'}, status=400)

    try:
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=bytes.fromhex(challenge_hex),
            expected_origin=settings.WEBAUTHN_ORIGIN,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            credential_public_key=bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception:
        logger.exception("WebAuthn authentication verification failed")
        return JsonResponse({'error': 'Authentication failed.'}, status=400)

    cred.sign_count = verification.new_sign_count
    cred.save(update_fields=['sign_count'])

    request.session.pop(_UNLOCK_ATTEMPT_KEY, None)
    request.session.pop(_UNLOCK_LOCKOUT_KEY, None)
    request.session['portfolio_unlocked_at'] = time.time()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def webauthn_remove(request):
    """Remove a registered biometric credential."""
    if not request.user.can_view_portfolio:
        return JsonResponse({'error': 'Forbidden.'}, status=403)
    unlocked_at = request.session.get('portfolio_unlocked_at')
    if not unlocked_at or (time.time() - unlocked_at) > _PORTFOLIO_UNLOCK_TTL:
        return JsonResponse({'error': 'Portfolio must be unlocked.'}, status=403)

    try:
        pk = int(json.loads(request.body).get('id', 0))
        WebAuthnCredential.objects.filter(pk=pk, user=request.user).delete()
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    return JsonResponse({'ok': True})
