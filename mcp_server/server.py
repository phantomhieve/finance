"""
Vault Finance — MCP Server

Exposes all Vault financial data as MCP resources (read-only) and provides
tools for writes with full audit logging via MCPAuditLog.

Run with:
    python manage.py run_mcp_server          (stdio, for Gemini CLI)
    mcp dev mcp_server/server.py             (dev inspector UI)
"""

import datetime
import json
import logging
import os
import sys
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Bootstrap Django before importing any models
# ---------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pftracker.settings')

# Ensure the project root is on sys.path so Django can find the apps
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env so DATABASE_URL etc. are available
try:
    from pftracker.dotenv import load_dotenv  # noqa: E402
    load_dotenv()
except ImportError:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_project_root, '.env'))
    except ImportError:
        pass

import django  # noqa: E402
django.setup()

# ---------------------------------------------------------------------------
# Now safe to import Django models and app code
# ---------------------------------------------------------------------------
from django.apps import apps as django_apps  # noqa: E402
from django.db.models import Sum, Case, When  # noqa: E402

from mcp.server import MCPServer  # noqa: E402
from mcp.types import Icon  # noqa: E402

from tracker.models import (  # noqa: E402
    AccountGroup, User, Transaction, Category,
    HRAExpense, FinancialGoal as TrackerGoal,
    GoalIncrement, MonthlyGoalAdjustment, Note,
    MonthlySavingsComment,
)
from portfolio.models import (  # noqa: E402
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding,
    CommodityPrice, MonthlySnapshot,
    FinancialGoal as PortfolioGoal, USStockHolding,
    PortfolioInsight, RealEstateHolding,
)
from jewellery.models import JewelleryItem  # noqa: E402
from portfolio.services import (  # noqa: E402
    get_portfolio_summary as _fetch_portfolio_summary,
    refresh_commodity_prices as _refresh_commodity_prices,
    refresh_us_stock_prices as _refresh_us_stock_prices,
)
from mcp_server.models import MCPAuditLog  # noqa: E402
from mcp_server.audit import (  # noqa: E402
    log_create, log_update, log_delete,
    serialize_instance, revert_entry,
)

# Logging — write to stderr, never stdout (stdio transport uses stdout)
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s %(name)s %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger('mcp_server')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZERO = Decimal('0')


def _json_serial(obj):
    """JSON serialiser for types json.dumps can't handle natively."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def _to_json(data) -> str:
    """Serialise data to a compact JSON string."""
    return json.dumps(data, default=_json_serial, ensure_ascii=False)


def _get_group():
    """Return the first AccountGroup (single-tenant app)."""
    return AccountGroup.objects.first()


def _get_primary_user():
    """Return the primary user for write operations."""
    return User.objects.filter(user_type='PRIMARY').first()


def _parse_date(date_str: str) -> datetime.date:
    """Parse a date string in YYYY-MM-DD format."""
    return datetime.date.fromisoformat(date_str)


def _parse_decimal(value) -> Decimal:
    """Parse a decimal value from string or number."""
    if value is None:
        return _ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO


def _qs_to_dicts(qs, fields):
    """Convert a queryset to a list of dicts with specified fields."""
    return list(qs.values(*fields))


def _model_to_dict(instance, exclude=None):
    """Convert a model instance to a dict, handling special types."""
    exclude = exclude or set()
    data = {}
    for field in instance._meta.concrete_fields:
        name = field.name
        if name in exclude:
            continue
        value = getattr(instance, name)
        if isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, (datetime.date, datetime.datetime)):
            value = value.isoformat()
        data[name] = value
    return data


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    name="Vault Finance",
    title="Vault Finance",
    description="Personal Finance & Portfolio Tracker MCP Server",
    version="1.0.0",
    website_url="https://localhost:8000",
    icons=[
        Icon(
            src="https://localhost:8000/static/icons/icon-512.png",
            mime_type="image/png",
            sizes=["512x512"],
        )
    ],
)


# =====================================================================
#  RESOURCES — Read-only data access
# =====================================================================

@mcp.resource("vault://portfolio/summary")
def portfolio_summary() -> str:
    """Full portfolio summary: total value, per-asset breakdown, P&L, goals, equity split, consolidated view."""
    group = _get_group()
    summary = _fetch_portfolio_summary(group=group)

    # Convert to serialisable format (strip Django objects)
    result = {
        'total_value': str(summary['total_value']),
        'total_invested': str(summary['total_invested']),
        'total_returns': str(summary['total_returns']),
        'return_pct': str(summary['return_pct']),
        'assets': [
            {'name': a['name'], 'value': str(a['value']), 'pct': str(a['pct'])}
            for a in summary['assets']
        ],
        'equity_total': str(summary['equity_total']),
        'equity_invested': str(summary['equity_invested']),
        'equity_returns': str(summary['equity_returns']),
        'equity_items': [
            {'name': e['name'], 'value': str(e['value']), 'pct': str(e['pct'])}
            for e in summary['equity_items']
        ],
        'consolidated': [
            {'name': c['name'], 'value': str(c['value']), 'pct': str(c['pct'])}
            for c in summary['consolidated']
        ],
        'goals': summary['goals'],
        'epf_balance': str(summary['epf_balance']),
        'nps_balance': str(summary.get('nps_latest').total_balance if summary.get('nps_latest') else 0),
        'fd_principal': str(summary['fd_principal']),
        'fd_current': str(summary['fd_current']),
        'cash_total': str(summary['cash_total']),
        'bonds_total': str(summary['bonds_total']),
        'crypto_invested': str(summary['crypto_invested']),
        'crypto_current': str(summary['crypto_current']),
        'commodity_total': str(summary['commodity_total']),
        'gold_rate_per_gram': str(summary['gold_rate']),
        'silver_rate_per_gram': str(summary['silver_rate']),
        'us_stocks_invested': str(summary['us_stocks_invested']),
        'us_stocks_current': str(summary['us_stocks_current']),
        'real_estate_invested': str(summary['real_estate_invested']),
        'real_estate_current': str(summary['real_estate_current']),
        'real_estate_returns': str(summary['real_estate_returns']),
    }
    return _to_json(result)


@mcp.resource("vault://portfolio/stocks")
def portfolio_stocks() -> str:
    """All stock holdings across all Zerodha accounts."""
    group = _get_group()
    accounts = ZerodhaAccount.objects.filter(group=group) if group else ZerodhaAccount.objects.all()
    result = []
    for acct in accounts:
        for h in acct.stock_holdings.all():
            result.append({
                'account': acct.name,
                'symbol': h.symbol,
                'quantity': h.quantity,
                'purchase_value': str(h.purchase_value),
                'current_value': str(h.current_value),
                'pnl': str(h.pnl),
                'pnl_pct': str(h.pnl_pct),
                'is_baby': h.is_baby,
            })
    return _to_json(result)


@mcp.resource("vault://portfolio/mutual-funds")
def portfolio_mutual_funds() -> str:
    """All mutual fund holdings (index + other) across all Zerodha accounts."""
    group = _get_group()
    accounts = ZerodhaAccount.objects.filter(group=group) if group else ZerodhaAccount.objects.all()
    result = []
    for acct in accounts:
        for h in acct.mf_holdings.all():
            result.append({
                'account': acct.name,
                'fund_name': h.fund_name,
                'fund_type': h.fund_type,
                'units': str(h.units),
                'purchase_value': str(h.purchase_value),
                'current_value': str(h.current_value),
                'pnl': str(h.pnl),
                'pnl_pct': str(h.pnl_pct),
                'is_baby': h.is_baby,
            })
    return _to_json(result)


@mcp.resource("vault://portfolio/epf")
def portfolio_epf() -> str:
    """EPF entries and running balance."""
    group = _get_group()
    qs = EPFEntry.objects.filter(group=group) if group else EPFEntry.objects.all()
    entries = [_model_to_dict(e) for e in qs[:50]]
    total_contrib = qs.filter(entry_type='CONTRIBUTION').aggregate(t=Sum('amount'))['t'] or _ZERO
    total_interest = qs.filter(entry_type='INTEREST').aggregate(t=Sum('amount'))['t'] or _ZERO
    return _to_json({
        'total_contribution': str(total_contrib),
        'total_interest': str(total_interest),
        'balance': str(total_contrib + total_interest),
        'entries': entries,
    })


@mcp.resource("vault://portfolio/nps")
def portfolio_nps() -> str:
    """NPS entries and current balance."""
    group = _get_group()
    qs = NPSEntry.objects.filter(group=group) if group else NPSEntry.objects.all()
    latest = qs.order_by('-date', '-created_at').first()
    entries = [_model_to_dict(e) for e in qs[:50]]
    return _to_json({
        'current_balance': str(latest.total_balance if latest else 0),
        'total_contribution': str(qs.aggregate(t=Sum('contribution'))['t'] or 0),
        'total_interest': str(qs.aggregate(t=Sum('interest_earned'))['t'] or 0),
        'entries': entries,
    })


@mcp.resource("vault://portfolio/fixed-deposits")
def portfolio_fixed_deposits() -> str:
    """All fixed deposits (active and inactive)."""
    group = _get_group()
    qs = FixedDeposit.objects.filter(group=group) if group else FixedDeposit.objects.all()
    result = []
    for fd in qs:
        d = _model_to_dict(fd)
        d['current_value'] = str(fd.current_value)
        d['maturity_value'] = str(fd.maturity_value)
        d['interest_accrued'] = str(fd.interest_accrued)
        d['days_remaining'] = fd.days_remaining
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://portfolio/cash")
def portfolio_cash() -> str:
    """Cash positions."""
    group = _get_group()
    qs = CashPosition.objects.filter(group=group) if group else CashPosition.objects.all()
    return _to_json([_model_to_dict(c) for c in qs])


@mcp.resource("vault://portfolio/bonds")
def portfolio_bonds() -> str:
    """Bond holdings."""
    group = _get_group()
    qs = BondHolding.objects.filter(group=group) if group else BondHolding.objects.all()
    return _to_json([_model_to_dict(b) for b in qs])


@mcp.resource("vault://portfolio/crypto")
def portfolio_crypto() -> str:
    """Crypto holdings."""
    group = _get_group()
    qs = CryptoHolding.objects.filter(group=group) if group else CryptoHolding.objects.all()
    result = []
    for c in qs:
        d = _model_to_dict(c)
        d['pnl'] = str(c.pnl)
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://portfolio/commodities")
def portfolio_commodities() -> str:
    """Commodity (gold/silver) holdings with current market prices."""
    group = _get_group()
    qs = CommodityHolding.objects.filter(group=group) if group else CommodityHolding.objects.all()
    prices = {p.commodity_type: str(p.rate_per_gram) for p in CommodityPrice.objects.all()}
    result = []
    for h in qs:
        d = _model_to_dict(h)
        d['purchase_value'] = str(h.purchase_value)
        d['current_value'] = str(h.current_value)
        d['current_rate'] = str(h.current_rate)
        result.append(d)
    return _to_json({'prices_per_gram': prices, 'holdings': result})


@mcp.resource("vault://portfolio/us-stocks")
def portfolio_us_stocks() -> str:
    """US stock (RSU) holdings."""
    group = _get_group()
    qs = USStockHolding.objects.filter(group=group) if group else USStockHolding.objects.all()
    result = []
    for h in qs:
        d = _model_to_dict(h)
        d['purchase_value_inr'] = str(h.purchase_value)
        d['current_value_inr'] = str(h.current_value)
        d['pnl'] = str(h.pnl)
        d['pnl_pct'] = str(h.pnl_pct)
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://portfolio/real-estate")
def portfolio_real_estate() -> str:
    """Real estate property investments (land, plots, apartments, commercial)."""
    group = _get_group()
    qs = RealEstateHolding.objects.filter(group=group) if group else RealEstateHolding.objects.all()
    result = []
    for h in qs:
        d = _model_to_dict(h)
        d['area_in_gaj'] = str(h.area_in_gaj)
        d['area_in_sqft'] = str(h.area_in_sqft)
        d['area_display'] = h.area_display
        d['total_cost_basis'] = str(h.total_cost_basis)
        d['purchase_rate_per_gaj'] = str(h.purchase_rate_per_gaj)
        d['current_rate_per_gaj'] = str(h.current_rate_per_gaj)
        d['pnl'] = str(h.pnl)
        d['pnl_pct'] = str(h.pnl_pct)
        d['cagr_pct'] = str(h.cagr_pct)
        d['annual_rental_income'] = str(h.annual_rental_income)
        d['rental_yield_pct'] = str(h.rental_yield_pct)
        d['location_summary'] = h.location_summary_for_llm
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://portfolio/goals")
def portfolio_goals() -> str:
    """Portfolio financial goals and progress."""
    group = _get_group()
    qs = PortfolioGoal.objects.filter(group=group) if group else PortfolioGoal.objects.all()
    return _to_json([_model_to_dict(g) for g in qs])


@mcp.resource("vault://portfolio/snapshots")
def portfolio_snapshots() -> str:
    """Monthly portfolio snapshots (growth data). Returns last 24 months."""
    group = _get_group()
    qs = MonthlySnapshot.objects.filter(group=group) if group else MonthlySnapshot.objects.all()
    result = []
    for s in qs[:24]:
        d = _model_to_dict(s)
        d['return_pct'] = str(s.return_pct)
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://tracker/transactions/{fy_year}")
def tracker_transactions(fy_year: str) -> str:
    """Savings transactions for a financial year (e.g. fy_year=2025 for FY 2025-26)."""
    try:
        fy = int(fy_year)
    except ValueError:
        return _to_json({'error': f'Invalid fy_year: {fy_year}. Use YYYY format (e.g. 2025).'})
    start = datetime.date(fy, 4, 1)
    end = datetime.date(fy + 1, 3, 31)
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = Transaction.objects.filter(
        user__group=user.group, date__gte=start, date__lte=end,
    ).select_related('category')
    result = []
    for t in qs:
        result.append({
            'id': t.id,
            'date': t.date.isoformat(),
            'amount': str(t.amount),
            'type': t.type,
            'category': t.category.name if t.category else None,
            'category_type': t.category.type if t.category else None,
            'remarks': t.remarks,
        })
    return _to_json({
        'fy': f'FY {fy}-{str(fy + 1)[-2:]}',
        'count': len(result),
        'transactions': result,
    })


@mcp.resource("vault://tracker/hra/{fy_year}")
def tracker_hra(fy_year: str) -> str:
    """HRA expenses for a financial year."""
    try:
        fy = int(fy_year)
    except ValueError:
        return _to_json({'error': f'Invalid fy_year: {fy_year}.'})
    start = datetime.date(fy, 4, 1)
    end = datetime.date(fy + 1, 3, 31)
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = HRAExpense.objects.filter(
        user__group=user.group, date__gte=start, date__lte=end,
    )
    return _to_json([_model_to_dict(h) for h in qs])


@mcp.resource("vault://tracker/goals")
def tracker_goals() -> str:
    """Monthly savings goals, increments, and adjustments."""
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    goals = [_model_to_dict(g) for g in TrackerGoal.objects.filter(user=user)]
    increments = [_model_to_dict(i) for i in GoalIncrement.objects.filter(user=user)]
    adjustments = [_model_to_dict(a) for a in MonthlyGoalAdjustment.objects.filter(user=user)]
    comments = [_model_to_dict(c) for c in MonthlySavingsComment.objects.filter(user=user)]
    return _to_json({
        'goals': goals,
        'increments': increments,
        'adjustments': adjustments,
        'comments': comments,
    })


@mcp.resource("vault://tracker/notes")
def tracker_notes() -> str:
    """Personal notes (last 100)."""
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = Note.objects.filter(user__group=user.group)[:100]
    return _to_json([_model_to_dict(n) for n in qs])


@mcp.resource("vault://jewellery/items")
def jewellery_items() -> str:
    """All jewellery items with estimated values."""
    group = _get_group()
    qs = JewelleryItem.objects.filter(group=group) if group else JewelleryItem.objects.all()
    result = []
    for item in qs:
        d = _model_to_dict(item, exclude={'photo'})
        d['display_label'] = item.display_label
        d['estimated_value'] = str(item.estimated_value)
        result.append(d)
    return _to_json(result)


@mcp.resource("vault://mcp/audit-log")
def mcp_audit_log() -> str:
    """Recent MCP audit log entries (last 50)."""
    entries = MCPAuditLog.objects.all()[:50]
    result = []
    for e in entries:
        result.append({
            'id': e.id,
            'timestamp': e.timestamp.isoformat(),
            'action': e.action,
            'model_name': e.model_name,
            'object_id': e.object_id,
            'object_repr': e.object_repr,
            'tool_name': e.tool_name,
            'reverted': e.reverted,
            'reverted_at': e.reverted_at.isoformat() if e.reverted_at else None,
            'data_before': e.data_before,
            'data_after': e.data_after,
        })
    return _to_json(result)


# =====================================================================
#  TOOLS — Read operations (Data queries)
# =====================================================================

@mcp.tool()
def get_portfolio_summary() -> str:
    """Get complete portfolio summary: total net worth, invested value, total returns, P&L %, asset breakdown, goals, and consolidated holdings."""
    return portfolio_summary()


@mcp.tool()
def get_portfolio_stocks(symbol: str = "", account_name: str = "") -> str:
    """Get all stock holdings across Zerodha accounts with purchase values, current market values, and P&L.

    Args:
        symbol: Optional stock symbol filter (e.g. 'TCS', 'INFY')
        account_name: Optional Zerodha account name filter
    """
    group = _get_group()
    accounts = ZerodhaAccount.objects.filter(group=group) if group else ZerodhaAccount.objects.all()
    if account_name:
        accounts = accounts.filter(name__icontains=account_name)
    result = []
    for acct in accounts:
        holdings = acct.stock_holdings.all()
        if symbol:
            holdings = holdings.filter(symbol__icontains=symbol)
        for h in holdings:
            result.append({
                'account': acct.name,
                'symbol': h.symbol,
                'quantity': h.quantity,
                'purchase_value': str(h.purchase_value),
                'current_value': str(h.current_value),
                'pnl': str(h.pnl),
                'pnl_pct': str(h.pnl_pct),
                'is_baby': h.is_baby,
            })
    return _to_json(result)


@mcp.tool()
def get_portfolio_mutual_funds(fund_name: str = "", account_name: str = "") -> str:
    """Get all mutual fund holdings across Zerodha accounts.

    Args:
        fund_name: Optional fund name filter
        account_name: Optional account name filter
    """
    group = _get_group()
    accounts = ZerodhaAccount.objects.filter(group=group) if group else ZerodhaAccount.objects.all()
    if account_name:
        accounts = accounts.filter(name__icontains=account_name)
    result = []
    for acct in accounts:
        holdings = acct.mf_holdings.all()
        if fund_name:
            holdings = holdings.filter(fund_name__icontains=fund_name)
        for h in holdings:
            result.append({
                'account': acct.name,
                'fund_name': h.fund_name,
                'fund_type': h.fund_type,
                'units': str(h.units),
                'purchase_value': str(h.purchase_value),
                'current_value': str(h.current_value),
                'pnl': str(h.pnl),
                'pnl_pct': str(h.pnl_pct),
                'is_baby': h.is_baby,
            })
    return _to_json(result)


@mcp.tool()
def get_epf_details() -> str:
    """Get EPF (Employee Provident Fund) running balance, total contribution, total interest, and recent entries."""
    return portfolio_epf()


@mcp.tool()
def get_nps_details() -> str:
    """Get NPS (National Pension System) current balance, total contribution, total interest, and recent entries."""
    return portfolio_nps()


@mcp.tool()
def get_fixed_deposits(is_active_only: bool = True) -> str:
    """Get fixed deposits with principal, interest rate, maturity date, accrued interest, current value, and days remaining.

    Args:
        is_active_only: Whether to return only active FDs (default: True)
    """
    group = _get_group()
    qs = FixedDeposit.objects.filter(group=group) if group else FixedDeposit.objects.all()
    if is_active_only:
        qs = qs.filter(is_active=True)
    result = []
    for fd in qs:
        d = _model_to_dict(fd)
        d['current_value'] = str(fd.current_value)
        d['maturity_value'] = str(fd.maturity_value)
        d['interest_accrued'] = str(fd.interest_accrued)
        d['days_remaining'] = fd.days_remaining
        result.append(d)
    return _to_json(result)


@mcp.tool()
def get_cash_positions() -> str:
    """Get all cash positions and bank account balances."""
    return portfolio_cash()


@mcp.tool()
def get_bond_holdings() -> str:
    """Get all bond holdings."""
    return portfolio_bonds()


@mcp.tool()
def get_crypto_holdings() -> str:
    """Get all crypto holdings with invested amount, current value, and P&L."""
    return portfolio_crypto()


@mcp.tool()
def get_commodity_holdings() -> str:
    """Get physical gold and silver commodity holdings with current market prices and value."""
    return portfolio_commodities()


@mcp.tool()
def get_us_stock_holdings() -> str:
    """Get US stock (RSU) holdings with INR values and P&L."""
    return portfolio_us_stocks()


@mcp.tool()
def get_real_estate_holdings() -> str:
    """Get all real estate property investments (plots, apartments, commercial, villas, agricultural) with measurements in Gaj/SqFt, acquisition costs, current valuation, and returns."""
    return portfolio_real_estate()


@mcp.tool()
def get_real_estate_detail(holding_id: int) -> str:
    """Get detailed structured data and LLM research metadata for a specific real estate property.

    Args:
        holding_id: ID of the RealEstateHolding record
    """
    group = _get_group()
    try:
        h = RealEstateHolding.objects.get(pk=holding_id, group=group) if group else RealEstateHolding.objects.get(pk=holding_id)
    except RealEstateHolding.DoesNotExist:
        return f"Error: RealEstateHolding #{holding_id} not found."

    d = _model_to_dict(h)
    d['area_in_gaj'] = str(h.area_in_gaj)
    d['area_in_sqft'] = str(h.area_in_sqft)
    d['area_display'] = h.area_display
    d['total_cost_basis'] = str(h.total_cost_basis)
    d['purchase_rate_per_gaj'] = str(h.purchase_rate_per_gaj)
    d['current_rate_per_gaj'] = str(h.current_rate_per_gaj)
    d['pnl'] = str(h.pnl)
    d['pnl_pct'] = str(h.pnl_pct)
    d['cagr_pct'] = str(h.cagr_pct)
    d['annual_rental_income'] = str(h.annual_rental_income)
    d['rental_yield_pct'] = str(h.rental_yield_pct)
    d['location_summary'] = h.location_summary_for_llm
    d['llm_research_prompt'] = h.get_llm_research_prompt()
    return _to_json(d)


@mcp.tool()
def get_real_estate_llm_prompt(holding_id: int) -> str:
    """Get a ready-to-run market research prompt for Gemini/LLMs to analyze circle rates, price growth, and catalysts for a property.

    Args:
        holding_id: ID of the RealEstateHolding record
    """
    group = _get_group()
    try:
        h = RealEstateHolding.objects.get(pk=holding_id, group=group) if group else RealEstateHolding.objects.get(pk=holding_id)
    except RealEstateHolding.DoesNotExist:
        return f"Error: RealEstateHolding #{holding_id} not found."

    return h.get_llm_research_prompt()


@mcp.tool()
def get_portfolio_goals() -> str:
    """Get portfolio milestone goals and progress."""
    return portfolio_goals()


@mcp.tool()
def get_portfolio_snapshots(limit: int = 12) -> str:
    """Get monthly portfolio snapshots to see net worth and returns growth over time.

    Args:
        limit: Number of monthly snapshots to return (default: 12)
    """
    limit = min(max(1, limit), 60)
    group = _get_group()
    qs = MonthlySnapshot.objects.filter(group=group) if group else MonthlySnapshot.objects.all()
    result = []
    for s in qs[:limit]:
        d = _model_to_dict(s)
        d['return_pct'] = str(s.return_pct)
        result.append(d)
    return _to_json(result)


@mcp.tool()
def get_transactions(
    fy_year: str = "",
    limit: int = 50,
    category_name: str = "",
    type: str = "",
) -> str:
    """Get transactions (savings, expenses, transfers, extra income) with optional filters.

    Args:
        fy_year: Optional financial year filter (e.g. '2025' for FY 2025-26)
        limit: Max transactions to return (default: 50, max: 200)
        category_name: Optional category name filter
        type: Optional type filter (SAVINGS, EXPENSE, TRANSFER, EXTRA_INCOME)
    """
    limit = min(max(1, limit), 200)
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = Transaction.objects.filter(user__group=user.group).select_related('category')
    if fy_year:
        try:
            fy = int(fy_year)
            start = datetime.date(fy, 4, 1)
            end = datetime.date(fy + 1, 3, 31)
            qs = qs.filter(date__gte=start, date__lte=end)
        except ValueError:
            return _to_json({'error': f'Invalid fy_year: {fy_year}. Use YYYY format (e.g. 2025).'})
    if category_name:
        qs = qs.filter(category__name__icontains=category_name)
    if type:
        qs = qs.filter(type=type.upper())
    result = []
    for t in qs[:limit]:
        result.append({
            'id': t.id,
            'date': t.date.isoformat(),
            'amount': str(t.amount),
            'type': t.type,
            'category': t.category.name if t.category else None,
            'category_type': t.category.type if t.category else None,
            'remarks': t.remarks,
        })
    return _to_json({'count': len(result), 'transactions': result})


@mcp.tool()
def get_hra_expenses(fy_year: str = "") -> str:
    """Get House Rent Allowance (HRA) expenses.

    Args:
        fy_year: Optional financial year (e.g. '2025' for FY 2025-26)
    """
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = HRAExpense.objects.filter(user__group=user.group)
    if fy_year:
        try:
            fy = int(fy_year)
            start = datetime.date(fy, 4, 1)
            end = datetime.date(fy + 1, 3, 31)
            qs = qs.filter(date__gte=start, date__lte=end)
        except ValueError:
            return _to_json({'error': f'Invalid fy_year: {fy_year}.'})
    return _to_json([_model_to_dict(h) for h in qs])


@mcp.tool()
def get_tracker_goals() -> str:
    """Get monthly savings goals, increments, and adjustments."""
    return tracker_goals()


@mcp.tool()
def get_notes(
    limit: int = 50,
    section: str = "",
    pending_only: bool = False,
) -> str:
    """Get personal notes, todo items, or pending credit/debit trackers.

    Args:
        limit: Max notes to return (default: 50, max: 100)
        section: Optional section filter (e.g. 'Savings', 'Tax', 'Goal')
        pending_only: If true, only return notes with pending CREDIT/DEBIT amounts
    """
    limit = min(max(1, limit), 100)
    user = _get_primary_user()
    if not user:
        return _to_json({'error': 'No primary user found.'})
    qs = Note.objects.filter(user__group=user.group)
    if section:
        qs = qs.filter(section__icontains=section)
    if pending_only:
        qs = qs.filter(pending_type__in=['CREDIT', 'DEBIT']).exclude(pending_amount=0)
    return _to_json([_model_to_dict(n) for n in qs[:limit]])


@mcp.tool()
def get_jewellery_items(
    category: str = "",
    metal_type: str = "",
    location: str = "",
) -> str:
    """Get all jewellery items with weights, purity, locker/safe location, and estimated market values.

    Args:
        category: Optional filter (e.g. 'CHAIN', 'RING', 'BANGLE', 'COIN')
        metal_type: Optional filter ('GOLD', 'SILVER', 'PLATINUM', 'DIAMOND_OTHER')
        location: Optional filter ('BANK_LOCKER', 'HOME_SAFE')
    """
    group = _get_group()
    qs = JewelleryItem.objects.filter(group=group) if group else JewelleryItem.objects.all()
    if category:
        qs = qs.filter(category=category.upper())
    if metal_type:
        qs = qs.filter(metal_type=metal_type.upper())
    if location:
        qs = qs.filter(location=location.upper())
    result = []
    for item in qs:
        d = _model_to_dict(item, exclude={'photo'})
        d['display_label'] = item.display_label
        d['estimated_value'] = str(item.estimated_value)
        result.append(d)
    return _to_json(result)


# =====================================================================
#  TOOLS — Write operations (all audit-logged)
# =====================================================================

@mcp.tool()
def add_transaction(
    date: str,
    amount: str,
    type: str,
    category_name: str = "",
    remarks: str = "",
) -> str:
    """Add a savings/expense/transfer/income transaction.

    Args:
        date: Transaction date in YYYY-MM-DD format
        amount: Transaction amount (positive number)
        type: One of SAVINGS, EXPENSE, TRANSFER, EXTRA_INCOME
        category_name: Category name (must exist). Leave empty if none.
        remarks: Optional remarks
    """
    user = _get_primary_user()
    if not user:
        return "Error: No primary user found."

    valid_types = ['SAVINGS', 'TRANSFER', 'EXTRA_INCOME', 'EXPENSE']
    if type.upper() not in valid_types:
        return f"Error: type must be one of {valid_types}"

    category = None
    if category_name:
        category = Category.objects.filter(user=user, name__iexact=category_name).first()
        if not category:
            available = list(Category.objects.filter(user=user).values_list('name', flat=True))
            return f"Error: Category '{category_name}' not found. Available: {available}"

    txn = Transaction(
        user=user,
        date=_parse_date(date),
        amount=_parse_decimal(amount),
        type=type.upper(),
        category=category,
        remarks=remarks,
    )
    txn.save()
    log_create(txn, 'add_transaction')
    return _to_json({
        'status': 'created',
        'id': txn.id,
        'summary': str(txn),
    })


@mcp.tool()
def update_transaction(
    txn_id: int,
    amount: str = None,
    date: str = None,
    type: str = None,
    category_name: str = None,
    remarks: str = None,
) -> str:
    """Update an existing savings/expense/transfer/income transaction.

    Args:
        txn_id: ID of the transaction to update
        amount: New transaction amount (optional)
        date: New date in YYYY-MM-DD format (optional)
        type: SAVINGS, EXPENSE, TRANSFER, or EXTRA_INCOME (optional)
        category_name: Category name (optional)
        remarks: Updated remarks (optional)
    """
    user = _get_primary_user()
    try:
        txn = Transaction.objects.get(pk=txn_id, user=user) if user else Transaction.objects.get(pk=txn_id)
    except Transaction.DoesNotExist:
        return f"Error: Transaction #{txn_id} not found."

    old_data = serialize_instance(txn)
    if amount is not None and amount != "":
        txn.amount = _parse_decimal(amount)
    if date is not None and date != "":
        txn.date = _parse_date(date)
    if type is not None and type != "":
        valid_types = ['SAVINGS', 'TRANSFER', 'EXTRA_INCOME', 'EXPENSE']
        if type.upper() not in valid_types:
            return f"Error: type must be one of {valid_types}"
        txn.type = type.upper()
    if category_name is not None and category_name != "":
        category = Category.objects.filter(user=txn.user, name__iexact=category_name).first()
        if not category:
            available = list(Category.objects.filter(user=txn.user).values_list('name', flat=True))
            return f"Error: Category '{category_name}' not found. Available: {available}"
        txn.category = category
    elif category_name == "":
        txn.category = None
    if remarks is not None:
        txn.remarks = remarks

    txn.save()
    log_update(txn, old_data, 'update_transaction')
    return _to_json({'status': 'updated', 'id': txn.id, 'summary': str(txn)})


@mcp.tool()
def add_hra_entry(
    date: str,
    amount: str,
    remarks: str = "",
) -> str:
    """Add a House Rent Allowance (HRA) expense.

    Args:
        date: Date in YYYY-MM-DD format
        amount: Rent amount
        remarks: Optional remarks
    """
    user = _get_primary_user()
    if not user:
        return "Error: No primary user found."

    entry = HRAExpense(
        user=user,
        date=_parse_date(date),
        amount=_parse_decimal(amount),
        remarks=remarks,
    )
    entry.save()
    log_create(entry, 'add_hra_entry')
    return _to_json({
        'status': 'created',
        'id': entry.id,
        'summary': str(entry),
    })


@mcp.tool()
def update_hra_entry(
    entry_id: int,
    amount: str = "",
    date: str = "",
    expense_type: str = "",
    mode_of_payment: str = "",
    remarks: str = "",
) -> str:
    """Update an existing HRA rent or expense entry.

    Args:
        entry_id: ID of the HRA entry to update
        amount: New amount (optional)
        date: New date in YYYY-MM-DD format (optional)
        expense_type: Description/type (optional)
        mode_of_payment: Payment method (optional)
        remarks: Updated remarks (optional)
    """
    user = _get_primary_user()
    try:
        entry = HRAExpense.objects.get(pk=entry_id, user=user) if user else HRAExpense.objects.get(pk=entry_id)
    except HRAExpense.DoesNotExist:
        return f"Error: HRA expense #{entry_id} not found."

    old_data = serialize_instance(entry)
    if amount:
        entry.amount = _parse_decimal(amount)
    if date:
        entry.date = _parse_date(date)
    if expense_type:
        entry.expense_type = expense_type
    if mode_of_payment:
        entry.mode_of_payment = mode_of_payment
    if remarks:
        entry.remarks = remarks

    entry.save()
    log_update(entry, old_data, 'update_hra_entry')
    return _to_json({'status': 'updated', 'id': entry.id, 'summary': str(entry)})


@mcp.tool()
def add_note(
    title: str,
    date: str,
    body: str = "",
    section: str = "",
    amount: str = "",
    pending_type: str = "",
    initial_amount: str = "",
) -> str:
    """Create a personal note.

    Args:
        title: Note title
        date: Note date in YYYY-MM-DD format
        body: Note body text (optional)
        section: Section tag like 'Savings', 'Tax', 'Goal' (optional)
        amount: Optional linked amount
        pending_type: CREDIT (To Receive) or DEBIT (To Pay) — leave empty for regular notes
        initial_amount: Initial pending amount (required if pending_type is set)
    """
    user = _get_primary_user()
    if not user:
        return "Error: No primary user found."

    note = Note(
        user=user,
        title=title,
        date=_parse_date(date),
        body=body,
        section=section,
    )
    if amount:
        note.amount = _parse_decimal(amount)
    if pending_type and pending_type.upper() in ('CREDIT', 'DEBIT'):
        note.pending_type = pending_type.upper()
        if initial_amount:
            note.initial_amount = _parse_decimal(initial_amount)
            note.pending_amount = note.initial_amount
    note.save()
    log_create(note, 'add_note')
    return _to_json({'status': 'created', 'id': note.id, 'summary': str(note)})


@mcp.tool()
def update_note(
    note_id: int,
    title: str = "",
    body: str = "",
    section: str = "",
    amount: str = "",
    is_done: bool = False,
) -> str:
    """Update an existing note.

    Args:
        note_id: ID of the note to update
        title: New title (leave empty to keep current)
        body: New body text (leave empty to keep current)
        section: New section tag (leave empty to keep current)
        amount: New amount (leave empty to keep current)
        is_done: Mark as done (for todo-type notes)
    """
    try:
        note = Note.objects.get(pk=note_id)
    except Note.DoesNotExist:
        return f"Error: Note #{note_id} not found."

    old_data = serialize_instance(note)
    if title:
        note.title = title
    if body:
        note.body = body
    if section:
        note.section = section
    if amount:
        note.amount = _parse_decimal(amount)
    if is_done and not note.is_done:
        from django.utils import timezone as tz
        note.is_done = True
        note.done_at = tz.now()
    note.save()
    log_update(note, old_data, 'update_note')
    return _to_json({'status': 'updated', 'id': note.id, 'summary': str(note)})


@mcp.tool()
def add_epf_entry(
    date: str,
    amount: str,
    entry_type: str = "CONTRIBUTION",
    remarks: str = "",
) -> str:
    """Add an EPF contribution or interest entry.

    Args:
        date: Entry date in YYYY-MM-DD format
        amount: Amount in INR
        entry_type: CONTRIBUTION or INTEREST
        remarks: Optional remarks
    """
    group = _get_group()
    if entry_type.upper() not in ('CONTRIBUTION', 'INTEREST'):
        return "Error: entry_type must be CONTRIBUTION or INTEREST"

    entry = EPFEntry(
        group=group,
        date=_parse_date(date),
        amount=_parse_decimal(amount),
        entry_type=entry_type.upper(),
        remarks=remarks,
    )
    entry.save()
    log_create(entry, 'add_epf_entry')
    return _to_json({'status': 'created', 'id': entry.id, 'summary': str(entry)})


@mcp.tool()
def update_epf_entry(
    entry_id: int,
    amount: str = "",
    date: str = "",
    entry_type: str = "",
    remarks: str = "",
) -> str:
    """Update an existing EPF contribution or interest entry.

    Args:
        entry_id: ID of the EPF entry
        amount: New amount in INR (optional)
        date: New date in YYYY-MM-DD format (optional)
        entry_type: CONTRIBUTION or INTEREST (optional)
        remarks: Updated remarks (optional)
    """
    group = _get_group()
    try:
        entry = EPFEntry.objects.get(pk=entry_id, group=group) if group else EPFEntry.objects.get(pk=entry_id)
    except EPFEntry.DoesNotExist:
        return f"Error: EPF entry #{entry_id} not found."

    old_data = serialize_instance(entry)
    if amount:
        entry.amount = _parse_decimal(amount)
    if date:
        entry.date = _parse_date(date)
    if entry_type:
        if entry_type.upper() not in ('CONTRIBUTION', 'INTEREST'):
            return "Error: entry_type must be CONTRIBUTION or INTEREST"
        entry.entry_type = entry_type.upper()
    if remarks:
        entry.remarks = remarks

    entry.save()
    log_update(entry, old_data, 'update_epf_entry')
    return _to_json({'status': 'updated', 'id': entry.id, 'summary': str(entry)})


@mcp.tool()
def add_nps_entry(
    date: str,
    contribution: str,
    interest_earned: str,
    total_balance: str,
    remarks: str = "",
) -> str:
    """Add an NPS update entry.

    Args:
        date: Entry date in YYYY-MM-DD format
        contribution: Money added in this update
        interest_earned: Returns credited in this update
        total_balance: Running total after this update
        remarks: Optional remarks
    """
    group = _get_group()
    entry = NPSEntry(
        group=group,
        date=_parse_date(date),
        contribution=_parse_decimal(contribution),
        interest_earned=_parse_decimal(interest_earned),
        total_balance=_parse_decimal(total_balance),
        remarks=remarks,
    )
    entry.save()
    log_create(entry, 'add_nps_entry')
    return _to_json({'status': 'created', 'id': entry.id, 'summary': str(entry)})


@mcp.tool()
def update_nps_entry(
    entry_id: int,
    date: str = "",
    contribution: str = "",
    interest_earned: str = "",
    total_balance: str = "",
    remarks: str = "",
) -> str:
    """Update an existing NPS snapshot entry.

    Args:
        entry_id: ID of the NPS entry
        date: New date in YYYY-MM-DD format (optional)
        contribution: Updated contribution amount (optional)
        interest_earned: Updated returns/interest credited (optional)
        total_balance: Updated total running balance (optional)
        remarks: Updated remarks (optional)
    """
    group = _get_group()
    try:
        entry = NPSEntry.objects.get(pk=entry_id, group=group) if group else NPSEntry.objects.get(pk=entry_id)
    except NPSEntry.DoesNotExist:
        return f"Error: NPS entry #{entry_id} not found."

    old_data = serialize_instance(entry)
    if date:
        entry.date = _parse_date(date)
    if contribution:
        entry.contribution = _parse_decimal(contribution)
    if interest_earned:
        entry.interest_earned = _parse_decimal(interest_earned)
    if total_balance:
        entry.total_balance = _parse_decimal(total_balance)
    if remarks:
        entry.remarks = remarks

    entry.save()
    log_update(entry, old_data, 'update_nps_entry')
    return _to_json({'status': 'updated', 'id': entry.id, 'summary': str(entry)})


@mcp.tool()
def add_fixed_deposit(
    name: str,
    account_name: str,
    principal: str,
    interest_rate: str,
    start_date: str,
    maturity_date: str,
    compounding: str = "QUARTERLY",
    is_baby: bool = False,
    remarks: str = "",
) -> str:
    """Create a new fixed deposit.

    Args:
        name: FD name/description
        account_name: Bank account name (e.g. 'Atul Acc', 'HUF Acc')
        principal: Principal amount in INR
        interest_rate: Annual interest rate in % (e.g. '7.5')
        start_date: Start date in YYYY-MM-DD format
        maturity_date: Maturity date in YYYY-MM-DD format
        compounding: SIMPLE, MONTHLY, QUARTERLY, or ANNUAL (default: QUARTERLY)
        is_baby: Track in Child portfolio (default: false)
        remarks: Optional remarks
    """
    group = _get_group()
    valid_comp = ['SIMPLE', 'MONTHLY', 'QUARTERLY', 'ANNUAL']
    if compounding.upper() not in valid_comp:
        return f"Error: compounding must be one of {valid_comp}"

    fd = FixedDeposit(
        group=group,
        name=name,
        account_name=account_name,
        principal=_parse_decimal(principal),
        interest_rate=_parse_decimal(interest_rate),
        start_date=_parse_date(start_date),
        maturity_date=_parse_date(maturity_date),
        compounding=compounding.upper(),
        is_baby=is_baby,
        remarks=remarks,
    )
    fd.save()
    log_create(fd, 'add_fixed_deposit')
    return _to_json({
        'status': 'created', 'id': fd.id, 'summary': str(fd),
        'current_value': str(fd.current_value),
        'maturity_value': str(fd.maturity_value),
    })


@mcp.tool()
def update_fixed_deposit(
    fd_id: int,
    is_active: bool = True,
    remarks: str = "",
) -> str:
    """Update an existing fixed deposit (e.g. mark as inactive on maturity).

    Args:
        fd_id: ID of the fixed deposit
        is_active: Set to false to mark as matured/closed
        remarks: Updated remarks
    """
    try:
        fd = FixedDeposit.objects.get(pk=fd_id)
    except FixedDeposit.DoesNotExist:
        return f"Error: FD #{fd_id} not found."

    old_data = serialize_instance(fd)
    fd.is_active = is_active
    if remarks:
        fd.remarks = remarks
    fd.save()
    log_update(fd, old_data, 'update_fixed_deposit')
    return _to_json({'status': 'updated', 'id': fd.id, 'summary': str(fd)})


@mcp.tool()
def add_cash_position(
    name: str,
    amount: str,
    remarks: str = "",
    is_baby: bool = False,
) -> str:
    """Add a cash position.

    Args:
        name: Position name (e.g. 'Kanika Acc', 'Cash lent Reshu')
        amount: Amount in INR
        remarks: Optional remarks
        is_baby: Track in Child portfolio (default: false)
    """
    group = _get_group()
    pos = CashPosition(
        group=group,
        name=name,
        amount=_parse_decimal(amount),
        remarks=remarks,
        is_baby=is_baby,
    )
    pos.save()
    log_create(pos, 'add_cash_position')
    return _to_json({'status': 'created', 'id': pos.id, 'summary': str(pos)})


@mcp.tool()
def update_cash_position(
    position_id: int,
    amount: str = "",
    name: str = "",
    remarks: str = "",
) -> str:
    """Update an existing cash position.

    Args:
        position_id: ID of the cash position
        amount: New amount (leave empty to keep current)
        name: New name (leave empty to keep current)
        remarks: New remarks (leave empty to keep current)
    """
    try:
        pos = CashPosition.objects.get(pk=position_id)
    except CashPosition.DoesNotExist:
        return f"Error: Cash position #{position_id} not found."

    old_data = serialize_instance(pos)
    if amount:
        pos.amount = _parse_decimal(amount)
    if name:
        pos.name = name
    if remarks:
        pos.remarks = remarks
    pos.save()
    log_update(pos, old_data, 'update_cash_position')
    return _to_json({'status': 'updated', 'id': pos.id, 'summary': str(pos)})


@mcp.tool()
def add_bond_holding(
    account_name: str,
    amount: str,
    remarks: str = "",
    is_baby: bool = False,
) -> str:
    """Add a bond holding.

    Args:
        account_name: Account/platform name
        amount: Bond value in INR
        remarks: Optional remarks
        is_baby: Track in Child portfolio (default: false)
    """
    group = _get_group()
    bond = BondHolding(
        group=group,
        account_name=account_name,
        amount=_parse_decimal(amount),
        remarks=remarks,
        is_baby=is_baby,
    )
    bond.save()
    log_create(bond, 'add_bond_holding')
    return _to_json({'status': 'created', 'id': bond.id, 'summary': str(bond)})


@mcp.tool()
def update_bond_holding(
    bond_id: int,
    amount: str = "",
    remarks: str = "",
) -> str:
    """Update an existing bond holding.

    Args:
        bond_id: ID of the bond holding
        amount: New amount (leave empty to keep current)
        remarks: New remarks (leave empty to keep current)
    """
    try:
        bond = BondHolding.objects.get(pk=bond_id)
    except BondHolding.DoesNotExist:
        return f"Error: Bond #{bond_id} not found."

    old_data = serialize_instance(bond)
    if amount:
        bond.amount = _parse_decimal(amount)
    if remarks:
        bond.remarks = remarks
    bond.save()
    log_update(bond, old_data, 'update_bond_holding')
    return _to_json({'status': 'updated', 'id': bond.id, 'summary': str(bond)})


@mcp.tool()
def add_crypto_holding(
    name: str,
    amount_invested: str,
    current_value: str,
    remarks: str = "",
    is_baby: bool = False,
) -> str:
    """Add a crypto holding.

    Args:
        name: Crypto name (e.g. 'Bitcoin', 'Ethereum')
        amount_invested: Amount invested in INR
        current_value: Current value in INR
        remarks: Optional remarks
        is_baby: Track in Child portfolio (default: false)
    """
    group = _get_group()
    crypto = CryptoHolding(
        group=group,
        name=name,
        amount_invested=_parse_decimal(amount_invested),
        current_value=_parse_decimal(current_value),
        remarks=remarks,
        is_baby=is_baby,
    )
    crypto.save()
    log_create(crypto, 'add_crypto_holding')
    return _to_json({'status': 'created', 'id': crypto.id, 'summary': str(crypto)})


@mcp.tool()
def update_crypto_holding(
    crypto_id: int,
    current_value: str = "",
    amount_invested: str = "",
    remarks: str = "",
) -> str:
    """Update an existing crypto holding.

    Args:
        crypto_id: ID of the crypto holding
        current_value: New current value (leave empty to keep current)
        amount_invested: New invested amount (leave empty to keep current)
        remarks: New remarks (leave empty to keep current)
    """
    try:
        crypto = CryptoHolding.objects.get(pk=crypto_id)
    except CryptoHolding.DoesNotExist:
        return f"Error: Crypto #{crypto_id} not found."

    old_data = serialize_instance(crypto)
    if current_value:
        crypto.current_value = _parse_decimal(current_value)
    if amount_invested:
        crypto.amount_invested = _parse_decimal(amount_invested)
    if remarks:
        crypto.remarks = remarks
    crypto.save()
    log_update(crypto, old_data, 'update_crypto_holding')
    return _to_json({'status': 'updated', 'id': crypto.id, 'summary': str(crypto)})


@mcp.tool()
def add_commodity_holding(
    commodity_type: str,
    description: str,
    weight_grams: str,
    purchase_price_per_gram: str,
    purity: str = "24k",
    is_baby: bool = False,
) -> str:
    """Add a commodity (gold/silver) holding.

    Args:
        commodity_type: GOLD or SILVER
        description: Description (e.g. '20gm Coin - 1 (24k)')
        weight_grams: Weight in grams
        purchase_price_per_gram: Purchase price per gram in INR
        purity: For gold: 24k, 22k, 18k, 14k. For silver: 999, 925, 900, 800. Default: 24k
        is_baby: Track in Child portfolio (default: false)
    """
    group = _get_group()
    if commodity_type.upper() not in ('GOLD', 'SILVER'):
        return "Error: commodity_type must be GOLD or SILVER"

    holding = CommodityHolding(
        group=group,
        commodity_type=commodity_type.upper(),
        description=description,
        weight_grams=_parse_decimal(weight_grams),
        purchase_price_per_gram=_parse_decimal(purchase_price_per_gram),
        purity=purity,
        is_baby=is_baby,
    )
    holding.save()
    log_create(holding, 'add_commodity_holding')
    return _to_json({
        'status': 'created', 'id': holding.id, 'summary': str(holding),
        'purchase_value': str(holding.purchase_value),
    })


@mcp.tool()
def update_commodity_holding(
    holding_id: int,
    description: str = "",
    weight_grams: str = "",
    purchase_price_per_gram: str = "",
    purity: str = "",
    is_baby: bool = None,
) -> str:
    """Update an existing gold or silver commodity holding.

    Args:
        holding_id: ID of the commodity holding
        description: Updated description (optional)
        weight_grams: Updated weight in grams (optional)
        purchase_price_per_gram: Updated purchase price per gram in INR (optional)
        purity: Updated purity (24k, 22k, 18k, 14k, 999, 925, etc.) (optional)
        is_baby: Track in Child portfolio vs Master portfolio (optional)
    """
    group = _get_group()
    try:
        holding = CommodityHolding.objects.get(pk=holding_id, group=group) if group else CommodityHolding.objects.get(pk=holding_id)
    except CommodityHolding.DoesNotExist:
        return f"Error: Commodity holding #{holding_id} not found."

    old_data = serialize_instance(holding)
    if description:
        holding.description = description
    if weight_grams:
        holding.weight_grams = _parse_decimal(weight_grams)
    if purchase_price_per_gram:
        holding.purchase_price_per_gram = _parse_decimal(purchase_price_per_gram)
    if purity:
        holding.purity = purity
    if is_baby is not None:
        holding.is_baby = is_baby

    holding.save()
    log_update(holding, old_data, 'update_commodity_holding')
    return _to_json({
        'status': 'updated', 'id': holding.id, 'summary': str(holding),
        'purchase_value': str(holding.purchase_value),
    })


@mcp.tool()
def add_us_stock(
    symbol: str,
    units: str,
    purchase_value: str,
    remarks: str = "",
    is_baby: bool = False,
) -> str:
    """Add a US stock (RSU) holding.

    Args:
        symbol: Stock symbol (e.g. 'GOOG')
        units: Number of shares
        purchase_value: Total purchase value in INR
        remarks: Optional remarks
        is_baby: Track in Child portfolio (default: false)
    """
    group = _get_group()

    holding = USStockHolding(
        group=group,
        symbol=symbol.upper(),
        units=_parse_decimal(units),
        purchase_value=_parse_decimal(purchase_value),
        remarks=remarks,
        is_baby=is_baby,
    )
    # Refresh current rate from DB if available (or it syncs later)
    rate = CommodityPrice.objects.filter(commodity_type='USD_INR').first()
    if rate:
        holding.current_usd_rate = rate.rate_per_gram  # USD_INR uses this field
    
    holding.save()
    log_create(holding, 'add_us_stock')
    return _to_json({
        'status': 'created', 'id': holding.id, 'summary': str(holding),
        'purchase_value': str(holding.purchase_value),
    })


@mcp.tool()
def update_us_stock(
    holding_id: int,
    symbol: str = "",
    units: str = "",
    purchase_value: str = "",
    remarks: str = "",
    is_baby: bool = None,
) -> str:
    """Update an existing US stock (RSU) holding.

    Args:
        holding_id: ID of the US stock holding
        symbol: Updated symbol (optional)
        units: Updated share units (optional)
        purchase_value: Updated purchase value in INR (optional)
        remarks: Updated remarks (optional)
        is_baby: Track in Child portfolio vs Master portfolio (optional)
    """
    group = _get_group()
    try:
        holding = USStockHolding.objects.get(pk=holding_id, group=group) if group else USStockHolding.objects.get(pk=holding_id)
    except USStockHolding.DoesNotExist:
        return f"Error: US stock holding #{holding_id} not found."

    old_data = serialize_instance(holding)
    if symbol:
        holding.symbol = symbol.upper()
    if units:
        holding.units = _parse_decimal(units)
    if purchase_value:
        holding.purchase_value = _parse_decimal(purchase_value)
    if remarks:
        holding.remarks = remarks
    if is_baby is not None:
        holding.is_baby = is_baby

    holding.save()
    log_update(holding, old_data, 'update_us_stock')
    return _to_json({
        'status': 'updated', 'id': holding.id, 'summary': str(holding),
        'purchase_value': str(holding.purchase_value),
    })


@mcp.tool()
def add_real_estate_holding(
    name: str,
    area_value: str,
    purchase_date: str,
    purchase_price: str,
    current_valuation: str,
    property_type: str = "PLOT_LAND",
    status: str = "VACANT_PLOT",
    area_unit: str = "GAJ",
    locality: str = "",
    city: str = "Noida",
    state: str = "Uttar Pradesh",
    landmark: str = "",
    pincode: str = "",
    micro_market_tag: str = "",
    google_maps_url: str = "",
    khasra_khata_number: str = "",
    stamp_duty_charges: str = "0",
    monthly_rental_income: str = "0",
    is_baby: bool = False,
    remarks: str = "",
) -> str:
    """Add a real estate property or land investment.

    Args:
        name: Name or description (e.g. 'Sector 150 Express Plot B-42')
        area_value: Land or property size (e.g. 200)
        purchase_date: Acquisition/registry date (YYYY-MM-DD)
        purchase_price: Base purchase amount in INR
        current_valuation: Current estimated market valuation in INR
        property_type: PLOT_LAND, APARTMENT_FLAT, COMMERCIAL, VILLA_HOUSE, AGRICULTURAL, or OTHER
        status: VACANT_PLOT, READY_SELF, RENTED, UNDER_CONSTRUCTION, or RESALE_PLANNED
        area_unit: GAJ (sq yards), SQFT, SQYD, ACRE, BIGHA, or SQMT (default: GAJ)
        locality: Locality or sector (e.g. 'Sector 150')
        city: City (default: 'Noida')
        state: State (default: 'Uttar Pradesh')
        landmark: Key landmark or proximity (optional)
        pincode: Postal code (optional)
        micro_market_tag: Micro-market tag or growth corridor (e.g. 'Yamuna Expressway')
        google_maps_url: Direct Google Maps link (optional)
        khasra_khata_number: Khasra / Khatauni / Registry document ID (optional)
        stamp_duty_charges: Stamp duty and registration charges in INR (default: 0)
        monthly_rental_income: Monthly rental yield in INR (default: 0)
        is_baby: Track in Child portfolio (default: false)
        remarks: Notes, builder info, tenant details (optional)
    """
    group = _get_group()
    holding = RealEstateHolding(
        group=group,
        name=name,
        property_type=property_type.upper(),
        status=status.upper(),
        area_value=_parse_decimal(area_value),
        area_unit=area_unit.upper(),
        locality=locality,
        city=city,
        state=state,
        landmark=landmark,
        pincode=pincode,
        micro_market_tag=micro_market_tag,
        google_maps_url=google_maps_url,
        khasra_khata_number=khasra_khata_number,
        purchase_date=_parse_date(purchase_date),
        purchase_price=_parse_decimal(purchase_price),
        stamp_duty_charges=_parse_decimal(stamp_duty_charges),
        current_valuation=_parse_decimal(current_valuation),
        last_valuation_date=datetime.date.today(),
        monthly_rental_income=_parse_decimal(monthly_rental_income),
        is_baby=is_baby,
        remarks=remarks,
    )
    holding.save()
    log_create(holding, 'add_real_estate_holding')
    return _to_json({
        'status': 'created',
        'id': holding.id,
        'summary': str(holding),
        'area': holding.area_display,
        'total_cost_basis': str(holding.total_cost_basis),
        'current_valuation': str(holding.current_valuation),
        'rate_per_gaj': str(holding.current_rate_per_gaj),
    })


@mcp.tool()
def update_real_estate_holding(
    holding_id: int,
    name: str = None,
    current_valuation: str = None,
    monthly_rental_income: str = None,
    status: str = None,
    landmark: str = None,
    micro_market_tag: str = None,
    google_maps_url: str = None,
    khasra_khata_number: str = None,
    remarks: str = None,
) -> str:
    """Update attributes or status of an existing real estate holding.

    Args:
        holding_id: Primary key of the RealEstateHolding
        name: Updated name (optional)
        current_valuation: Updated market price estimate in INR (optional)
        monthly_rental_income: Updated monthly rent in INR (optional)
        status: VACANT_PLOT, READY_SELF, RENTED, UNDER_CONSTRUCTION, RESALE_PLANNED (optional)
        landmark: Updated landmark (optional)
        micro_market_tag: Updated micro market tag (optional)
        google_maps_url: Updated Google Maps link (optional)
        khasra_khata_number: Updated legal doc number (optional)
        remarks: Updated notes (optional)
    """
    group = _get_group()
    try:
        holding = RealEstateHolding.objects.get(pk=holding_id, group=group) if group else RealEstateHolding.objects.get(pk=holding_id)
    except RealEstateHolding.DoesNotExist:
        return f"Error: RealEstateHolding #{holding_id} not found."

    old_state = serialize_instance(holding)
    if name is not None:
        holding.name = name
    if current_valuation is not None:
        holding.current_valuation = _parse_decimal(current_valuation)
        holding.last_valuation_date = datetime.date.today()
    if monthly_rental_income is not None:
        holding.monthly_rental_income = _parse_decimal(monthly_rental_income)
    if status is not None:
        holding.status = status.upper()
    if landmark is not None:
        holding.landmark = landmark
    if micro_market_tag is not None:
        holding.micro_market_tag = micro_market_tag
    if google_maps_url is not None:
        holding.google_maps_url = google_maps_url
    if khasra_khata_number is not None:
        holding.khasra_khata_number = khasra_khata_number
    if remarks is not None:
        holding.remarks = remarks

    holding.save()
    log_update(holding, old_state, 'update_real_estate_holding')
    return _to_json({
        'status': 'updated',
        'id': holding.id,
        'summary': str(holding),
        'current_valuation': str(holding.current_valuation),
        'current_rate_per_gaj': str(holding.current_rate_per_gaj),
    })


@mcp.tool()
def update_real_estate_valuation(
    holding_id: int,
    current_valuation: str,
    valuation_date: str = "",
    monthly_rental_income: str = None,
    notes: str = "",
) -> str:
    """Quickly update the latest appraisal valuation and rental income for a real estate holding.

    Args:
        holding_id: Primary key of the RealEstateHolding
        current_valuation: New market valuation estimate in INR
        valuation_date: Date of valuation appraisal (YYYY-MM-DD, defaults to today)
        monthly_rental_income: Optional updated monthly rental income in INR
        notes: Context or notes regarding the market price adjustment
    """
    group = _get_group()
    try:
        holding = RealEstateHolding.objects.get(pk=holding_id, group=group) if group else RealEstateHolding.objects.get(pk=holding_id)
    except RealEstateHolding.DoesNotExist:
        return f"Error: RealEstateHolding #{holding_id} not found."

    old_state = serialize_instance(holding)
    holding.current_valuation = _parse_decimal(current_valuation)
    holding.last_valuation_date = _parse_date(valuation_date) if valuation_date else datetime.date.today()
    if monthly_rental_income is not None:
        holding.monthly_rental_income = _parse_decimal(monthly_rental_income)
    if notes:
        holding.remarks = f"{holding.remarks}\n[Valuation {holding.last_valuation_date}]: {notes}".strip()

    holding.save()
    log_update(holding, old_state, 'update_real_estate_valuation')
    return _to_json({
        'status': 'updated',
        'id': holding.id,
        'name': holding.name,
        'current_valuation': str(holding.current_valuation),
        'current_rate_per_gaj': str(holding.current_rate_per_gaj),
        'pnl': str(holding.pnl),
        'pnl_pct': str(holding.pnl_pct),
        'cagr_pct': str(holding.cagr_pct),
    })


@mcp.tool()
def add_portfolio_goal(
    label: str,
    target_amount: str,
    notes: str = "",
) -> str:
    """Add a portfolio financial goal (milestone).

    Args:
        label: Goal label (e.g. '50L', '1Cr')
        target_amount: Target portfolio value in INR
        notes: Optional notes
    """
    group = _get_group()
    goal = PortfolioGoal(
        group=group,
        label=label,
        target_amount=_parse_decimal(target_amount),
        notes=notes,
    )
    goal.save()
    log_create(goal, 'add_portfolio_goal')
    return _to_json({'status': 'created', 'id': goal.id, 'summary': str(goal)})


@mcp.tool()
def update_portfolio_goal(
    goal_id: int,
    label: str = None,
    target_amount: str = None,
    achieved_date: str = None,
    is_achieved: bool = None,
    notes: str = None,
) -> str:
    """Update a portfolio financial milestone goal (e.g. 50L, 1Cr, 2Cr).

    Args:
        goal_id: ID of the PortfolioGoal
        label: Updated milestone label (e.g. '50L', '1Cr') (optional)
        target_amount: Updated target amount in INR (optional)
        achieved_date: Achievement date in YYYY-MM-DD format (optional)
        is_achieved: Mark as achieved (sets today's date) or unachieved (clears date) (optional)
        notes: Updated notes (optional)
    """
    group = _get_group()
    try:
        goal = PortfolioGoal.objects.get(pk=goal_id, group=group) if group else PortfolioGoal.objects.get(pk=goal_id)
    except PortfolioGoal.DoesNotExist:
        return f"Error: PortfolioGoal #{goal_id} not found."

    old_data = serialize_instance(goal)
    if label is not None and label != "":
        goal.label = label
    if target_amount is not None and target_amount != "":
        goal.target_amount = _parse_decimal(target_amount)
    if notes is not None:
        goal.notes = notes
    if achieved_date is not None and achieved_date != "":
        goal.achieved_at = _parse_date(achieved_date)
    elif is_achieved is not None:
        goal.achieved_at = datetime.date.today() if is_achieved else None

    goal.save()
    log_update(goal, old_data, 'update_portfolio_goal')
    return _to_json({
        'status': 'updated',
        'id': goal.id,
        'summary': str(goal),
        'label': goal.label,
        'target_amount': str(goal.target_amount),
        'achieved_at': str(goal.achieved_at) if goal.achieved_at else None,
        'notes': goal.notes,
    })


@mcp.tool()
def add_jewellery_item(
    category: str,
    metal_type: str,
    weight_grams: str,
    location: str = "BANK_LOCKER",
    purity: str = "22k",
    purchase_price: str = "0",
    purchase_date: str = "",
    notes: str = "",
) -> str:
    """Add a jewellery item.

    Args:
        category: CHAIN, LOCKET, NECKLACE, RING, BANGLE, BRACELET, EARRINGS, COIN, or OTHER
        metal_type: GOLD, SILVER, PLATINUM, or DIAMOND_OTHER
        weight_grams: Weight in grams
        location: BANK_LOCKER or HOME_SAFE (default: BANK_LOCKER)
        purity: For gold: 24k, 22k, 18k, 14k. For silver: 999, 925, 900, 800. Default: 22k
        purchase_price: Total purchase price in INR (default: 0)
        purchase_date: Purchase date in YYYY-MM-DD format (optional)
        notes: Optional notes
    """
    group = _get_group()
    valid_cats = ['CHAIN', 'LOCKET', 'NECKLACE', 'RING', 'BANGLE',
                  'BRACELET', 'EARRINGS', 'COIN', 'OTHER']
    if category.upper() not in valid_cats:
        return f"Error: category must be one of {valid_cats}"

    item = JewelleryItem(
        group=group,
        category=category.upper(),
        metal_type=metal_type.upper(),
        weight_grams=_parse_decimal(weight_grams),
        location=location.upper(),
        purity=purity,
        purchase_price=_parse_decimal(purchase_price),
        notes=notes,
    )
    if purchase_date:
        item.purchase_date = _parse_date(purchase_date)
    item.save()
    log_create(item, 'add_jewellery_item')
    return _to_json({
        'status': 'created', 'id': item.id,
        'label': item.display_label,
        'estimated_value': str(item.estimated_value),
    })


@mcp.tool()
def update_jewellery_item(
    item_id: int,
    category: str = "",
    metal_type: str = "",
    weight_grams: str = "",
    location: str = "",
    purity: str = "",
    purchase_price: str = "",
    purchase_date: str = "",
    notes: str = "",
) -> str:
    """Update an existing jewellery item.

    Args:
        item_id: ID of the jewellery item
        category: CHAIN, LOCKET, NECKLACE, RING, BANGLE, BRACELET, EARRINGS, COIN, or OTHER (optional)
        metal_type: GOLD, SILVER, PLATINUM, or DIAMOND_OTHER (optional)
        weight_grams: Weight in grams (optional)
        location: BANK_LOCKER or HOME_SAFE (optional)
        purity: Gold/Silver purity tag (optional)
        purchase_price: Total purchase price in INR (optional)
        purchase_date: Purchase date in YYYY-MM-DD format (optional)
        notes: Updated notes (optional)
    """
    group = _get_group()
    try:
        item = JewelleryItem.objects.get(pk=item_id, group=group) if group else JewelleryItem.objects.get(pk=item_id)
    except JewelleryItem.DoesNotExist:
        return f"Error: Jewellery item #{item_id} not found."

    old_data = serialize_instance(item)
    if category:
        valid_cats = ['CHAIN', 'LOCKET', 'NECKLACE', 'RING', 'BANGLE',
                      'BRACELET', 'EARRINGS', 'COIN', 'OTHER']
        if category.upper() not in valid_cats:
            return f"Error: category must be one of {valid_cats}"
        item.category = category.upper()
    if metal_type:
        item.metal_type = metal_type.upper()
    if weight_grams:
        item.weight_grams = _parse_decimal(weight_grams)
    if location:
        item.location = location.upper()
    if purity:
        item.purity = purity
    if purchase_price:
        item.purchase_price = _parse_decimal(purchase_price)
    if purchase_date:
        item.purchase_date = _parse_date(purchase_date)
    if notes:
        item.notes = notes

    item.save()
    log_update(item, old_data, 'update_jewellery_item')
    return _to_json({
        'status': 'updated',
        'id': item.id,
        'label': item.display_label,
        'estimated_value': str(item.estimated_value),
    })


@mcp.tool()
def delete_record(
    model_name: str,
    record_id: int,
) -> str:
    """Delete any MCP-supported record by model name and ID.

    Args:
        model_name: Model in 'app_label.ModelName' format (e.g. 'portfolio.FixedDeposit', 'tracker.Note')
        record_id: Primary key of the record to delete
    """
    # Allowlist of models that can be deleted via MCP
    allowed = {
        'tracker.Transaction', 'tracker.Note', 'tracker.HRAExpense',
        'portfolio.EPFEntry', 'portfolio.NPSEntry', 'portfolio.FixedDeposit',
        'portfolio.CashPosition', 'portfolio.BondHolding',
        'portfolio.CryptoHolding', 'portfolio.CommodityHolding',
        'portfolio.FinancialGoal', 'portfolio.USStockHolding',
        'portfolio.RealEstateHolding',
        'jewellery.JewelleryItem',
    }
    if model_name not in allowed:
        return f"Error: Deletion not allowed for '{model_name}'. Allowed: {sorted(allowed)}"

    try:
        Model = django_apps.get_model(model_name)
    except (LookupError, ValueError) as exc:
        return f"Error: Cannot resolve model '{model_name}': {exc}"

    try:
        obj = Model.objects.get(pk=record_id)
    except Model.DoesNotExist:
        return f"Error: {model_name}#{record_id} not found."

    obj_repr = str(obj)
    log_delete(obj, 'delete_record')
    obj.delete()
    return _to_json({
        'status': 'deleted',
        'model': model_name,
        'id': record_id,
        'was': obj_repr,
    })


@mcp.tool()
def revert_mcp_change(audit_log_id: int) -> str:
    """Revert a specific MCP audit log entry, undoing the change it describes.

    Args:
        audit_log_id: ID of the MCPAuditLog entry to revert
    """
    try:
        entry = MCPAuditLog.objects.get(pk=audit_log_id)
    except MCPAuditLog.DoesNotExist:
        return f"Error: Audit log entry #{audit_log_id} not found."

    result = revert_entry(entry)
    return _to_json({'status': 'reverted', 'detail': result})


@mcp.tool()
def list_mcp_audit_log(
    limit: int = 20,
    action: str = "",
    model_name: str = "",
) -> str:
    """List recent MCP audit log entries with optional filters.

    Args:
        limit: Number of entries to return (default: 20, max: 100)
        action: Filter by action: CREATE, UPDATE, or DELETE (optional)
        model_name: Filter by model name like 'portfolio.FixedDeposit' (optional)
    """
    limit = min(max(1, limit), 100)
    qs = MCPAuditLog.objects.all()
    if action:
        qs = qs.filter(action=action.upper())
    if model_name:
        qs = qs.filter(model_name=model_name)
    entries = []
    for e in qs[:limit]:
        entries.append({
            'id': e.id,
            'timestamp': e.timestamp.isoformat(),
            'action': e.action,
            'model_name': e.model_name,
            'object_id': e.object_id,
            'object_repr': e.object_repr,
            'tool_name': e.tool_name,
            'reverted': e.reverted,
        })
    return _to_json({'count': len(entries), 'entries': entries})


@mcp.tool()
def do_refresh_commodity_prices() -> str:
    """Trigger a refresh of gold and silver prices from external APIs."""
    result = _refresh_commodity_prices()
    if result:
        return _to_json({'status': 'refreshed', 'prices': result})
    return _to_json({'status': 'failed', 'detail': 'Could not fetch commodity prices.'})


@mcp.tool()
def do_refresh_us_stock_prices() -> str:
    """Trigger a refresh of US stock (RSU) prices and USD/INR rate."""
    group = _get_group()
    result = _refresh_us_stock_prices(group=group)
    if result:
        return _to_json({'status': 'refreshed', 'detail': result})
    return _to_json({'status': 'failed', 'detail': 'Could not fetch US stock prices.'})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport='stdio')
