"""Structured portfolio prompt data compilation for AI analysis."""
from __future__ import annotations

import datetime
import json
from decimal import Decimal

from ..models import MutualFundHolding, StockHolding


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


_ACTIVE_SIP_THRESHOLD = 100_000


def _holding_entry(h, account_name=None):
    """Build a standardised dict for a stock or MF holding."""
    pnl = float(h.current_value - h.purchase_value)
    inv = float(h.purchase_value)
    entry = {
        'invested': inv,
        'current': float(h.current_value),
        'pnl': pnl,
        'pnl_pct': round(pnl / inv * 100, 2) if inv else 0,
    }
    if account_name:
        entry['account'] = account_name
    return entry


def build_prompt_data(summary, growth, group):
    """Build the structured data payload for the AI prompt.

    Provides the AI model with every piece of data it needs to produce a
    thorough portfolio analysis: per-account breakdowns, active vs legacy
    MF classification, US stock RSU details, commodity item-level data,
    and month-by-month growth history.
    """
    total_value = float(summary['total_value'])

    asset_allocation = [
        {'name': a['name'], 'value': float(a['value']), 'pct': float(a['pct'])}
        for a in summary['assets']
    ]
    consolidated = [
        {'name': c['name'], 'value': float(c['value']), 'pct': float(c['pct'])}
        for c in summary['consolidated']
    ]

    equity = {
        'total': float(summary['equity_total']),
        'invested': float(summary['equity_invested']),
        'returns': float(summary['equity_returns']),
        'breakdown': [
            {'name': e['name'], 'value': float(e['value']), 'pct': float(e['pct'])}
            for e in summary['equity_items']
        ],
    }

    # ── Stocks: ALL holdings with per-account detail ──
    acct_map = {a['account'].id: a['account'].name for a in summary.get('accounts', [])}
    if group:
        stock_acct_ids = list(acct_map.keys())
        stocks_qs = StockHolding.objects.select_related('account').filter(
            account_id__in=stock_acct_ids).order_by('-current_value')
    else:
        stocks_qs = StockHolding.objects.select_related('account').order_by('-current_value')

    all_stocks = []
    for s in stocks_qs:
        entry = _holding_entry(s, s.account.name)
        entry['symbol'] = s.symbol
        entry['quantity'] = s.quantity
        all_stocks.append(entry)

    # Consolidated view: merge by symbol across accounts
    symbol_agg = {}
    for s in all_stocks:
        rec = symbol_agg.setdefault(s['symbol'], {
            'symbol': s['symbol'], 'total_qty': 0, 'total_invested': 0,
            'total_current': 0, 'accounts': [],
        })
        rec['total_qty'] += s['quantity']
        rec['total_invested'] += s['invested']
        rec['total_current'] += s['current']
        rec['accounts'].append(s['account'])
    stocks_consolidated = []
    for rec in sorted(symbol_agg.values(), key=lambda x: x['total_current'], reverse=True):
        pnl = rec['total_current'] - rec['total_invested']
        rec['total_pnl'] = pnl
        rec['total_pnl_pct'] = round(pnl / rec['total_invested'] * 100, 2) if rec['total_invested'] else 0
        rec['pct_of_portfolio'] = round(rec['total_current'] / total_value * 100, 2) if total_value else 0
        stocks_consolidated.append(rec)

    # ── Mutual Funds: ALL with active vs legacy classification ──
    if group:
        mf_qs = MutualFundHolding.objects.select_related('account').filter(
            account_id__in=stock_acct_ids).order_by('-current_value')
    else:
        mf_qs = MutualFundHolding.objects.select_related('account').order_by('-current_value')

    mutual_funds = []
    active_sip_funds = []
    legacy_funds = []
    for mf in mf_qs:
        entry = _holding_entry(mf, mf.account.name)
        entry['name'] = mf.fund_name
        entry['type'] = mf.fund_type
        is_active = float(mf.current_value) >= _ACTIVE_SIP_THRESHOLD
        entry['status'] = 'active_sip' if is_active else 'legacy'
        mutual_funds.append(entry)
        if is_active:
            active_sip_funds.append(entry)
        else:
            legacy_funds.append(entry)

    # ── US Stocks (RSU) ──
    us_stocks_list = list(summary.get('us_stocks', []))
    us_stocks = []
    for h in us_stocks_list:
        us_stocks.append({
            'symbol': h.symbol,
            'company': h.company_name,
            'quantity': h.quantity,
            'vest_date': h.vest_date.isoformat(),
            'purchase_price_usd': float(h.purchase_price_usd),
            'current_price_usd': float(h.current_price_usd),
            'purchase_usd_inr': float(h.purchase_usd_inr),
            'current_usd_inr': float(h.current_usd_inr),
            'invested_inr': float(h.purchase_value),
            'current_inr': float(h.current_value),
            'pnl_inr': float(h.pnl),
            'pnl_pct': float(h.pnl_pct),
            'remarks': h.remarks,
        })

    epf = {
        'balance': float(summary['epf_balance']),
        'contributions': float(summary['epf_total_contrib']),
        'interest': float(summary['epf_total_interest']),
    }

    nps_latest = summary['nps_latest']
    nps = {
        'balance': float(nps_latest.total_balance) if nps_latest else 0,
        'contributions': float(summary['nps_total_contrib']),
        'interest': float(summary['nps_total_interest']),
    }

    fixed_deposits = []
    for fd in summary['active_fds']:
        fixed_deposits.append({
            'name': fd.name,
            'account': fd.account_name,
            'principal': float(fd.principal),
            'rate': float(fd.interest_rate),
            'compounding': fd.compounding,
            'maturity_date': fd.maturity_date.isoformat(),
            'current_value': float(fd.current_value),
            'days_remaining': fd.days_remaining,
        })

    # ── Commodities: item-level detail ──
    gold_holdings = list(summary.get('gold_holdings', []))
    silver_holdings = list(summary.get('silver_holdings', []))
    gold_invested = sum(float(h.weight_grams) * float(h.purchase_price_per_gram) for h in gold_holdings)
    silver_invested = sum(float(h.weight_grams) * float(h.purchase_price_per_gram) for h in silver_holdings)

    commodities = {
        'gold': {
            'weight_grams': float(summary['gold_weight']),
            'rate_per_gram': float(summary['gold_rate']),
            'invested': gold_invested,
            'current_value': float(summary['gold_value']),
            'pnl': float(summary['gold_value']) - gold_invested,
            'items': [
                {'description': h.description, 'purity': h.purity,
                 'weight_grams': float(h.weight_grams),
                 'buy_per_gram': float(h.purchase_price_per_gram)}
                for h in gold_holdings
            ],
        },
        'silver': {
            'weight_grams': float(summary['silver_weight']),
            'rate_per_gram': float(summary['silver_rate']),
            'invested': silver_invested,
            'current_value': float(summary['silver_value']),
            'pnl': float(summary['silver_value']) - silver_invested,
            'items': [
                {'description': h.description, 'purity': h.purity,
                 'weight_grams': float(h.weight_grams),
                 'buy_per_gram': float(h.purchase_price_per_gram)}
                for h in silver_holdings
            ],
        },
        'total_pct_of_portfolio': round(
            float(summary['commodity_total']) / total_value * 100, 2
        ) if total_value else 0,
    }

    # ── Cash: with liquidity annotation ──
    cash_positions = list(summary['cash_positions'])
    cash = {
        'total': float(summary['cash_total']),
        'positions': [
            {'name': c.name, 'amount': float(c.amount),
             'remarks': c.remarks or ''}
            for c in cash_positions
        ],
    }
    bonds = {'total': float(summary['bonds_total'])}

    crypto_holdings = list(summary['crypto_holdings'])
    crypto = {
        'invested': float(summary['crypto_invested']),
        'current': float(summary['crypto_current']),
        'pnl': float(summary['crypto_current']) - float(summary['crypto_invested']),
        'holdings': [
            {'name': cr.name, 'invested': float(cr.amount_invested),
             'current': float(cr.current_value), 'remarks': cr.remarks}
            for cr in crypto_holdings
        ],
    }

    # ── Real Estate holdings ──
    re_holdings = list(summary.get('real_estate_holdings', []))
    re_total_cost = float(summary.get('real_estate_invested', 0))
    re_total_current = float(summary.get('real_estate_current', 0))
    re_total_pnl = re_total_current - re_total_cost
    re_total_area_gaj = sum(float(h.area_in_gaj) for h in re_holdings)
    re_total_annual_rental = sum(float(h.annual_rental_income) for h in re_holdings)

    real_estate = {
        'total_cost_basis': re_total_cost,
        'total_current': re_total_current,
        'total_pnl': re_total_pnl,
        'total_area_gaj': re_total_area_gaj,
        'total_annual_rental': re_total_annual_rental,
        'pct_of_portfolio': round(re_total_current / total_value * 100, 2) if total_value else 0,
        'holdings': [],
    }
    for h in re_holdings:
        re_entry = {
            'name': h.name,
            'property_type': h.get_property_type_display(),
            'status': h.get_status_display(),
            'acquisition_type': h.acquisition_type,
            'original_owner': h.original_owner or None,
            'inherited_year': h.inherited_year,
            'area_gaj': float(h.area_in_gaj),
            'area_sqft': float(h.area_in_sqft),
            'location_summary': h.location_summary_for_llm,
            'micro_market_tag': h.micro_market_tag or None,
            'landmark': h.landmark or None,
            'purchase_date': h.purchase_date.isoformat(),
            'cost_basis': float(h.total_cost_basis),
            'current_valuation': float(h.current_valuation),
            'cagr_pct': float(h.cagr_pct),
            'purchase_rate_per_gaj': float(h.purchase_rate_per_gaj),
            'current_rate_per_gaj': float(h.current_rate_per_gaj),
            'monthly_rental': float(h.monthly_rental_income or 0),
            'annual_rental': float(h.annual_rental_income),
            'rental_yield_pct': float(h.rental_yield_pct),
        }
        real_estate['holdings'].append(re_entry)

    goals = [
        {'financial_year': g['fy'], 'label': g['label'], 'target': g['target'],
         'progress_pct': g['pct'], 'status': g['status'],
         'monthly_needed': g.get('monthly_needed')}
        for g in summary['goals']
    ]

    growth_history = [
        {
            'month': m['name'],
            'total_value': m['total_value'],
            'invested': m['invested'],
            'returns': m['returns'],
            'money_added': m['money_added'],
            'returns_gained': m['returns_gained'],
        }
        for m in growth['months']
        if m['snapshot'] is not None
    ]

    # ── Per-account summary ──
    account_summaries = []
    for a in summary.get('accounts', []):
        account_summaries.append({
            'name': a['account'].name,
            'stocks_value': float(a['stocks']),
            'index_mf_value': float(a['index_mf']),
            'other_mf_value': float(a['other_mf']),
            'total': float(a['total']),
            'invested': float(a['invested']),
            'returns': float(a['returns']),
        })

    return {
        'portfolio_date': datetime.date.today().isoformat(),
        'summary': {
            'total_value': total_value,
            'total_invested': float(summary['total_invested']),
            'total_returns': float(summary['total_returns']),
            'return_pct': float(summary['return_pct']),
        },
        'asset_allocation': asset_allocation,
        'consolidated': consolidated,
        'equity': equity,
        'zerodha_accounts': account_summaries,
        'stocks_all': all_stocks,
        'stocks_consolidated': stocks_consolidated,
        'mutual_funds_all': mutual_funds,
        'mutual_funds_active_sip': active_sip_funds,
        'mutual_funds_legacy': legacy_funds,
        'us_stocks_rsu': us_stocks,
        'us_stocks_total': {
            'invested_inr': float(summary.get('us_stocks_invested', 0)),
            'current_inr': float(summary.get('us_stocks_current', 0)),
            'pnl_inr': float(summary.get('us_stocks_returns', 0)),
        },
        'epf': epf,
        'nps': nps,
        'fixed_deposits': fixed_deposits,
        'commodities': commodities,
        'real_estate': real_estate,
        'cash': cash,
        'bonds': bonds,
        'crypto': crypto,
        'goals': goals,
        'growth_history': growth_history,
    }
