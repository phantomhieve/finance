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
    fy_start_year, fy_label, get_google_credentials_path,
)
from .models import (
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding,
    CommodityPrice, MonthlySnapshot, FinancialGoal,
    USStockHolding,
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


def get_commodity_summary(group=None):
    """Aggregate commodity holdings into gold/silver weights, values, and P&L."""
    prices = {p.commodity_type: p for p in CommodityPrice.objects.filter(
        commodity_type__in=('GOLD', 'SILVER'),
    )}
    gold_price = prices.get('GOLD')
    silver_price = prices.get('SILVER')
    gold_rate = gold_price.rate_per_gram if gold_price else _ZERO
    silver_rate = silver_price.rate_per_gram if silver_price else _ZERO

    gold_qs = _gf(CommodityHolding.objects.filter(commodity_type='GOLD'), group)
    silver_qs = _gf(CommodityHolding.objects.filter(commodity_type='SILVER'), group)
    gold_weight = _sum_qs(gold_qs, 'weight_grams')
    silver_weight = _sum_qs(silver_qs, 'weight_grams')
    gold_value = (gold_weight * gold_rate).quantize(_ROUND2) if gold_rate else _ZERO
    silver_value = (silver_weight * silver_rate).quantize(_ROUND2) if silver_rate else _ZERO
    total = gold_value + silver_value

    invested = _gf(CommodityHolding.objects, group).aggregate(
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


def _zerodha_account_sums(z_accounts):
    """Batch-fetch per-account current/purchase sums for stocks and MFs (6 queries → dict)."""
    def _agg(qs, field):
        return dict(qs.values_list('account_id').annotate(t=Sum(field)))

    stock_qs = StockHolding.objects.filter(account__in=z_accounts)
    index_qs = MutualFundHolding.objects.filter(account__in=z_accounts, fund_type='INDEX')
    other_qs = MutualFundHolding.objects.filter(account__in=z_accounts, fund_type='OTHER')

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
# Portfolio summary
# ---------------------------------------------------------------------------

def get_portfolio_summary(group=None):
    """Aggregate every asset class into a master portfolio summary dict, scoped to group."""

    acct_ids = ZerodhaAccount.objects.filter(group=group).values_list('id', flat=True) if group else None
    if acct_ids is not None:
        stocks_qs = StockHolding.objects.filter(account_id__in=acct_ids)
        index_mf_qs = MutualFundHolding.objects.filter(account_id__in=acct_ids, fund_type='INDEX')
        other_mf_qs = MutualFundHolding.objects.filter(account_id__in=acct_ids, fund_type='OTHER')
    else:
        stocks_qs = StockHolding.objects.all()
        index_mf_qs = MutualFundHolding.objects.filter(fund_type='INDEX')
        other_mf_qs = MutualFundHolding.objects.filter(fund_type='OTHER')

    all_stocks_purchased = _sum_qs(stocks_qs, 'purchase_value')
    all_stocks_current = _sum_qs(stocks_qs, 'current_value')
    index_purchased = _sum_qs(index_mf_qs, 'purchase_value')
    index_current = _sum_qs(index_mf_qs, 'current_value')
    other_purchased = _sum_qs(other_mf_qs, 'purchase_value')
    other_current = _sum_qs(other_mf_qs, 'current_value')

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

    active_fds = list(_gf(FixedDeposit.objects.filter(is_active=True), group))
    fd_principal = sum(fd.principal for fd in active_fds)
    fd_current = sum(fd.current_value for fd in active_fds)

    cash_total = _sum_qs(_gf(CashPosition.objects, group).all(), 'amount')
    bonds_total = _sum_qs(_gf(BondHolding.objects, group).all(), 'amount')

    crypto_qs = _gf(CryptoHolding.objects, group).all()
    crypto_invested = _sum_qs(crypto_qs, 'amount_invested')
    crypto_current = _sum_qs(crypto_qs, 'current_value')

    us_stocks = list(_gf(USStockHolding.objects, group).all())
    us_stocks_invested = sum((h.purchase_value for h in us_stocks), _ZERO)
    us_stocks_current = sum((h.current_value for h in us_stocks), _ZERO)

    comm = get_commodity_summary(group)
    gold_rate = comm['gold_rate']
    silver_rate = comm['silver_rate']
    gold_weight = comm['gold_weight']
    silver_weight = comm['silver_weight']
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
        + commodity_invested + us_stocks_invested
    )
    total_returns = total_value - total_invested
    return_pct = _pct(total_returns, total_invested)

    # Financial goals
    goals = []
    for g in _gf(FinancialGoal.objects, group).all():
        target = float(g.target_amount)
        pct = min(float(total_value) / target * 100, 100) if target else 0
        goals.append({
            'id': g.id,
            'label': g.label,
            'target': target,
            'sort_order': g.sort_order,
            'pct': round(pct, 1),
            'achieved': pct >= 100,
        })

    # Zerodha account summaries (prefetch totals to avoid N+1)
    z_accounts = _gf(ZerodhaAccount.objects, group).all() if group else ZerodhaAccount.objects.all()
    acct_sums = _zerodha_account_sums(z_accounts)
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
        'goals': goals,
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
        'cash_positions': _gf(CashPosition.objects, group).order_by('-amount'),
        'cash_total': cash_total,
        'bonds': _gf(BondHolding.objects, group).order_by('-amount'),
        'bonds_total': bonds_total,
        'crypto_holdings': _gf(CryptoHolding.objects, group).order_by('-current_value'),
        'crypto_invested': crypto_invested,
        'crypto_current': crypto_current,
        'gold_holdings': _gf(CommodityHolding.objects.filter(commodity_type='GOLD'), group),
        'silver_holdings': _gf(CommodityHolding.objects.filter(commodity_type='SILVER'), group),
        **{k: comm[k] for k in (
            'gold_rate', 'silver_rate', 'gold_weight', 'silver_weight',
            'gold_value', 'silver_value', 'commodity_total',
            'commodity_invested', 'commodity_returns',
            'gold_price_obj', 'silver_price_obj',
        )},
        'epf_entries': _gf(EPFEntry.objects, group).all()[:10],
        'nps_entries': _gf(NPSEntry.objects, group).all()[:10],
        'us_stocks': us_stocks,
        'us_stocks_invested': us_stocks_invested,
        'us_stocks_current': us_stocks_current,
        'us_stocks_returns': us_stocks_current - us_stocks_invested,
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

    gc = gspread.service_account(filename=get_google_credentials_path())
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
