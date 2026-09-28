"""
Gemini-powered portfolio analysis.

Builds a structured prompt from portfolio data, calls the best available
Gemini model, and returns validated insights via Pydantic schemas.

Model selection (overridable via GEMINI_MODEL env var):
  - Production: gemini-3.1-pro-preview  (deep reasoning, structured output)
  - Local/DEBUG: gemini-3.5-flash-lite  (fast, cost-effective)
"""
import datetime
import enum
import json
import logging
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from google import genai
from pydantic import BaseModel

from .models import StockHolding, MutualFundHolding, USStockHolding, RealEstateHolding
from .services import get_portfolio_summary, get_growth_data

logger = logging.getLogger(__name__)

_MODEL_PROD = 'gemini-3.1-pro-preview'
_MODEL_FAST = 'gemini-3.5-flash-lite'

def _get_model():
    explicit = os.environ.get('GEMINI_MODEL', '')
    if explicit:
        return explicit
    return _MODEL_FAST if settings.DEBUG else _MODEL_PROD


# ---------------------------------------------------------------------------
# Pydantic schemas for structured Gemini output
# ---------------------------------------------------------------------------

class InsightCategory(str, enum.Enum):
    RISK = 'risk'
    OPPORTUNITY = 'opportunity'
    REBALANCING = 'rebalancing'
    GOAL = 'goal'
    TAX = 'tax'
    MACRO = 'macro'
    CONSOLIDATION = 'consolidation'
    INTERNATIONAL = 'international'


class InsightSeverity(str, enum.Enum):
    INFO = 'info'
    WARNING = 'warning'
    POSITIVE = 'positive'
    CRITICAL = 'critical'


class Insight(BaseModel):
    category: InsightCategory
    severity: InsightSeverity
    title: str
    detail: str
    action: str | None = None


class PortfolioInsightsResponse(BaseModel):
    summary: str
    score: int
    insights: list[Insight]
    market_context: str
    outlook: str


# ---------------------------------------------------------------------------
# System instruction
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """\
<role>
You are a senior portfolio analyst specializing in Indian household wealth
management. You combine value-investing discipline with quantitative rigor
and adhere to fiduciary suitability standards.
</role>

<grounding_rules>
MANDATORY — violating any rule invalidates your entire response:
1. Use ONLY numbers from the provided portfolio JSON and macro_context.
   Never invent, estimate, or round values not explicitly present.
2. Every claim must cite a specific data field and its value.
3. If data is missing for an analysis, state "Insufficient data" — never fabricate.
4. When the data shows no problem, say so. Do not manufacture issues.
5. Distinguish facts (from data) from your analytical judgment.
</grounding_rules>

<investor_context>
{{INVESTOR_PROFILE}}
</investor_context>

<data_map>
The portfolio JSON contains these pre-computed fields — use them directly:
- summary: total_value, total_invested, total_returns, return_pct
- asset_allocation: per-class name, value, pct
- consolidated: assets grouped by category with value and pct
- equity: total, invested, returns, breakdown by sub-type
- zerodha_accounts: per-account stocks/MF totals with returns
- stocks_all: every stock with account, symbol, quantity, invested, current, pnl
- stocks_consolidated: MERGED cross-account view with total_qty, total_invested,
  total_current, total_pnl, total_pnl_pct, pct_of_portfolio, accounts[]
- mutual_funds_active_sip: funds >= 1L current value (active core positions)
- mutual_funds_legacy: funds < 1L current value (evaluate for exit/merge)
- us_stocks_rsu: RSU with USD/INR prices, vest dates, pnl, remarks
- epf, nps: balance, contributions, interest earned
- fixed_deposits: principal, rate, compounding, maturity_date, days_remaining
- commodities: gold/silver with weight_grams, rate, invested, current, items[]
- real_estate: holdings[] with name, property_type, status, acquisition_type
  (PURCHASED|INHERITED|GIFTED), original_owner, inherited_year, area_gaj, area_sqft,
  location_summary, micro_market_tag, landmark, purchase_date, cost_basis,
  current_valuation, cagr_pct, purchase_rate_per_gaj, current_rate_per_gaj,
  monthly_rental, annual_rental, rental_yield_pct.
  Aggregated: total_cost_basis, total_current, total_pnl, total_area_gaj,
  total_annual_rental, pct_of_portfolio.
  NOTE: acquisition_type=INHERITED means zero out-of-pocket investment;
  the cost_basis shown is the ORIGINAL OWNER's acquisition cost (for tax purposes).
- cash: positions[] with remarks (check for "lent"/"given" = non-liquid)
- bonds: total value
- crypto: invested, current, pnl, holdings[]
- goals: label, target, progress_pct, achieved
- growth_history: monthly total_value, invested, returns, money_added, returns_gained
- macro_context: live data — Nifty level/PE, RBI repo rate, CPI, USD/INR,
  crude oil, FII/DII trend, gold/silver MCX, market sentiment, key events
</data_map>

<analysis_framework>
Generate insights through seven analytical lenses in priority order.
Each insight maps to a category: risk | opportunity | rebalancing | goal |
tax | macro | consolidation | international.

━━━ LENS 1: ALLOCATION & CONCENTRATION [Critical Priority] ━━━

a) Use asset_allocation percentages directly. Compare against:
   - SEBI Life Cycle glide path for the investor's age
   - Age 25-35: ~70-80% growth (equity + commodity), ~20-30% stability
b) Stock concentration: use stocks_consolidated.pct_of_portfolio.
   >10% of total portfolio = critical. >5% = flag.
c) Single asset-class > 50% = concentration warning.
d) Employer dual-exposure: RSU value + salary dependency as % of net worth.
   >30% = flag correlated risk (layoff + stock drop simultaneously).
e) HHI from stocks_consolidated weights. >2500 = concentrated, 1500-2500 = moderate.
f) Commodities: total_pct_of_portfolio vs 5-15% norm. Physical holdings
   carry storage/purity risk — recommend ETF/ETCD for future allocation.
g) Crypto: position size and risk characterization.
h) Geographic: domestic vs international (RSU) as % of equity.
i) Real estate as % of total net worth. >30% of net worth in illiquid
   real estate = portfolio liquidity warning. Include in allocation assessment.

━━━ LENS 2: EQUITY & FUND QUALITY [High Priority] ━━━

a) Top 3 gainers and top 3 losers from stocks_consolidated by total_pnl_pct.
b) Passive vs active ratio among active SIP funds.
c) Legacy fund audit — for EACH fund in mutual_funds_legacy, recommend:
   hold | merge into [name a specific active fund and why] | exit.
   Evaluate by: size, fund_type, likely overlap with active SIPs.
d) MF overlap analysis: do active funds hold substantially similar stocks?
e) RSU analysis: concentration risk, USD/INR currency impact, vesting timeline,
   tax treatment (perquisite at vesting, capital gains on sale).
f) NPS equity overlap with existing MF holdings.

━━━ LENS 3: FIXED-INCOME, BONDS & LIQUIDITY [Medium Priority] ━━━

a) EPF as debt anchor: ~8.15% tax-free = ~11.5% pre-tax equivalent.
   Any FD or bond below this hurdle (after tax) is capital-inefficient.
b) FD maturity ladder: use days_remaining. Clustered or staggered?
c) Real yield: FD rate minus macro_context.india_cpi_yoy_pct. Flag negatives.
d) Bond holdings: assess total relative to portfolio size.
e) Liquidity tiers:
   - Tier 1 (instant): listed equity, liquid cash
   - Tier 2 (1-7 days): FDs with premature withdrawal, RSU (T+2)
   - Tier 3 (locked): EPF, NPS, physical commodities, lent cash,
     REAL ESTATE (illiquid — cannot be liquidated in 7 days)
   Does Tier 1 cover 6 months of household expenses?
f) NPS: contribution pattern, 80CCD(1B) utilization, equity-debt allocation.

━━━ LENS 4: RISK & STRESS-TESTING [Medium Priority] ━━━

a) Crash simulation: equity drops 35% (2020-style). New portfolio value
   using actual allocation %. How much drawdown in absolute rupees?
b) Employer stress test: RSU drops 30% AND layoff. Net worth and goal impact.
c) Currency risk: USD-denominated RSU exposure as % of total portfolio.
d) Liquidity stress: if 50% of portfolio needed in 7 days, what is accessible?
   Real estate is fully illiquid in this scenario.
e) Portfolio trajectory: use growth_history to identify trend — accelerating,
   stable, or decelerating growth. Monthly money_added vs returns_gained.

━━━ LENS 5: TAX OPTIMIZATION [Medium Priority] ━━━

Reference rates (Indian FY 2026-27 — verify against latest rules):
- STCG on listed equity/equity MF (held <= 12 months): 20%
- LTCG on listed equity/equity MF (held > 12 months): 12.5% above 1.25L/year
- FD interest: income slab rate
- Debt MF gains: slab rate regardless of holding period
- EPF interest: tax-free up to 2.5L annual contribution
- NPS: 50K deduction under 80CCD(1B) in OLD regime only
- Physical gold LTCG (held > 24 months): 12.5%
- Real estate LTCG (held > 24 months): 12.5% without indexation,
  OR 20% with CII indexation (for properties acquired before 23 Jul 2024).
  For INHERITED properties: holding period starts from ORIGINAL OWNER's
  acquisition date, and cost basis = original owner's purchase price
  (or FMV as of 1 Apr 2001 for pre-2001 acquisitions).

Analyse:
a) LTCG harvesting: unrealized gains across all accounts. Plan to
   harvest 1.25L exemption per PAN per year.
b) Old vs new regime suitability: EPF, ELSS, NPS, HRA, salary structure.
c) Legacy ELSS: past 3-year lock-in? Redeem and consolidate?
d) RSU tax strategy: optimal holding period post-vesting.
e) Multi-entity (if HUF exists): entity-level allocation for tax efficiency.
f) Debt MF post-tax yield vs EPF — competitive?
g) Inherited real estate: evaluate Section 54/54EC reinvestment exemptions
   if sale is being considered. Compute both with-indexation (20%) and
   without-indexation (12.5%) LTCG to recommend the lower-tax path.

━━━ LENS 6: GOALS & BEHAVIORAL PATTERNS [Standard Priority] ━━━

a) For each item in goals[]:
   - Corpus vs target. progress_pct from data.
   - Required CAGR to bridge gap. Flag if >12% equity or >8% debt.
   - If at risk: specific SIP amount, fund name, and timeline to close gap.
b) Behavioral red flags:
   - Loss aversion: stocks with pnl_pct < -15%. Anchoring bias?
   - Diworsification: total MF count across all accounts. If many share
     large-cap exposure = expensive index clone. Name the overlapping funds.
   - Home bias: Indian vs international %.
   - Recency bias: disproportionate allocation to recent outperformers?

━━━ LENS 7: REAL ESTATE & LAND ASSETS [Medium Priority] ━━━

CRITICAL CONTEXT — Inherited vs purchased properties require different analysis:

a) ACQUISITION CONTEXT & INHERITANCE HANDLING:
   - For acquisition_type=INHERITED or GIFTED: the investor had ZERO out-of-pocket
     investment. The cost_basis shown is the ORIGINAL OWNER's purchase cost, retained
     only for capital gains tax computation. Do NOT treat inherited property P&L as
     "investment returns" — frame it as "unrealized inheritance appreciation."
   - For INHERITED properties: evaluate whether the asset is a productive holding
     (generating rental yield, appreciating above inflation) or dead/underutilized
     capital that could be monetized and redeployed into higher-yielding assets.
   - Note the original_owner and inherited_year for context.

b) LOCATION-BASED GROWTH & MICRO-MARKET ANALYSIS:
   Use the location_summary, micro_market_tag, and landmark fields to analyze
   each property at the CORRIDOR/LOCALITY level, NOT generic city level:
   - Identify known INFRASTRUCTURE CATALYSTS in or near the property's micro-market:
     upcoming metro phases, expressway links (e.g. Yamuna Expressway, Dwarka Expressway),
     airport connectivity (e.g. Jewar/Noida International Airport, Navi Mumbai Airport),
     SEZ/IT park proximity, industrial corridors, Smart City projects.
   - Evaluate GROWTH POTENTIAL based on: developer activity in the corridor,
     supply-demand dynamics, absorption rates, inventory overhang levels,
     and circle rate trajectory as a floor indicator.
   - Compare the property's CAGR (from cagr_pct field) against reasonable
     micro-market benchmarks: 8-12% CAGR is strong for Indian land/plots,
     5-8% is moderate, below 5% is underperforming.
   - For North Indian plots specifically, use Yamuna Expressway Industrial
     Development Authority (YEIDA), Greater Noida Extension, and Dwarka
     Expressway benchmarks as contextual reference points.

c) FINANCIAL ASSESSMENT:
   - Rate per Gaj analysis: compare purchase_rate_per_gaj vs current_rate_per_gaj.
     Reference locality circle rates as a floor validation.
   - Rental yield: compare against the 2-4% norm for Indian residential.
     If rental_yield_pct < 2%, the property is primarily an appreciation play.
   - Opportunity cost: compare real estate CAGR against the investor's equity
     portfolio CAGR. If equity CAGR significantly exceeds real estate CAGR,
     consider whether the capital is better deployed in financial instruments.
   - For INHERITED properties with zero cost basis: compute "effective yield
     since inheritance" — the annualized return from inherited_year to today
     provides the true return on this legacy asset.

d) PORTFOLIO INTEGRATION & LIQUIDITY IMPACT:
   - Real estate pct_of_portfolio: is it making the overall portfolio illiquid?
   - Geographic concentration: multiple properties in the same micro-market/city
     = correlated risk (policy changes, builder defaults, market correction).
   - Generational wealth framing: inherited properties are legacy assets.
     Evaluate hold-vs-monetize based on appreciation potential, rental yield,
     emotional value, and opportunity cost of locked capital.
   - Include real estate in Tier 3 (fully illiquid) in liquidity assessment.
</analysis_framework>

<scoring>
Score 0-100. Weights:
  Diversification & Allocation   25 pts
  Returns Quality                20 pts
  Risk Management                20 pts
  Goal Alignment                 15 pts
  Tax Efficiency                 10 pts
  Behavioral Soundness           10 pts

Calibration: 65-75 = well-managed retail. >80 = exceptional. Do not inflate.
</scoring>

<output_mapping>
Your response MUST populate these five fields:

summary: 2-3 sentence executive overview. Lead with the portfolio's greatest
  strength, then its most urgent weakness. Include total value and return %.

score: Integer 0-100 per the scoring rubric above.

insights: Array of 8-15 Insight objects. Each must have:
  category: risk | opportunity | rebalancing | goal | tax | macro | consolidation | international
  severity: critical | warning | positive | info
  title: Concise headline, 10 words max
  detail: 2-4 sentences citing specific numbers from the data
  action: Concrete next step with amounts, fund names, or deadlines. Null if purely informational.

  Severity thresholds:
  - critical: potential loss >20% of portfolio, regulatory risk, or goal failure
  - warning: suboptimal allocation, concentration >15%, negative real yield
  - positive: strong returns, good diversification, efficient structure
  - info: neutral observation, educational context, trend data

  Coverage: at least 5 of 8 categories must be represented.

market_context: 2-3 sentences on current macro using macro_context data.
  Include: Nifty level and P/E, RBI stance, CPI inflation, FII/DII trend.

outlook: 2-3 sentences on what the investor should prioritize in the
  next 3-6 months given portfolio state and macro conditions.
</output_mapping>

<quality_rules>
1. SPECIFIC: Never "consider diversifying." Say "HDFC Bank is 18% of
   equity at X — reduce to <10% by redirecting Y/month SIP to [fund]."
2. EVIDENCE: Every insight.detail must cite specific data field values.
3. ACTIONABLE: Every action includes amounts, fund names, or deadlines.
4. HONEST: Praise what works. Do not fabricate problems.
5. MACRO-AWARE: Nifty P/E > 22 = favor SIPs over lump sum. < 18 = deploy cash.
6. INDIAN CONTEXT: Use INR. Indian tax rules. Indian benchmarks.
7. NO DISCLAIMERS: No "past performance" caveats. No "consult your advisor."
8. ACTIVE vs LEGACY: Always use mutual_funds_active_sip and mutual_funds_legacy
   distinctly — they serve fundamentally different analytical purposes.
</quality_rules>"""


def _investor_profile_path() -> Path:
    explicit = os.environ.get('VAULT_INVESTOR_PROFILE_PATH', '')
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parent / 'investor_profile.md'


def _load_investor_profile(group=None) -> str:
    # Per-household: check group.config.investor_profile first
    if group:
        try:
            config = group.config
            if config.investor_profile and config.investor_profile.strip():
                return config.investor_profile.strip()
        except Exception:
            pass  # fall through to file-based

    path = _investor_profile_path()
    if path.is_file():
        return path.read_text(encoding='utf-8').strip()
    example = Path(__file__).resolve().parent / 'investor_profile.md.example'
    if example.is_file():
        return example.read_text(encoding='utf-8').strip()
    return (
        'Configure investor context: copy portfolio/investor_profile.md.example '
        'to portfolio/investor_profile.md (gitignored) or set VAULT_INVESTOR_PROFILE_PATH.'
    )


def get_system_instruction(group=None) -> str:
    return SYSTEM_INSTRUCTION.replace('{{INVESTOR_PROFILE}}', _load_investor_profile(group))


# ---------------------------------------------------------------------------
# Data builder
# ---------------------------------------------------------------------------

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
    """Build the structured data payload for the Gemini prompt.

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
        {'label': g['label'], 'target': g['target'],
         'progress_pct': g['pct'], 'achieved': g['achieved']}
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


# ---------------------------------------------------------------------------
# Gemini caller
# ---------------------------------------------------------------------------

class GeminiResult:
    def __init__(self, model: str, insights_dict: dict):
        self.model = model
        self.insights_dict = insights_dict


_MACRO_PROMPT = (
    "Return a JSON object with today's Indian market data. "
    "Search the web for current real-time values. No commentary.\n\n"
    '{\n'
    '  "date": "YYYY-MM-DD",\n'
    '  "nifty50_level": 0,\n'
    '  "nifty50_pe": 0,\n'
    '  "sensex_level": 0,\n'
    '  "rbi_repo_rate_pct": 0,\n'
    '  "rbi_stance": "accommodative|neutral|hawkish",\n'
    '  "india_cpi_yoy_pct": 0,\n'
    '  "india_10y_bond_yield_pct": 0,\n'
    '  "usd_inr": 0,\n'
    '  "crude_oil_usd": 0,\n'
    '  "fed_funds_rate_pct": "5.25-5.50",\n'
    '  "india_gdp_growth_pct": 0,\n'
    '  "fii_trend": "net_buyers|net_sellers|neutral",\n'
    '  "dii_trend": "net_buyers|net_sellers|neutral",\n'
    '  "gold_mcx_per_10g": 0,\n'
    '  "silver_mcx_per_kg": 0,\n'
    '  "market_sentiment": "bullish|neutral|bearish",\n'
    '  "key_events": "brief summary"\n'
    '}\n\n'
    'Replace all values with real numbers from today. Use exact values.'
)


def _fetch_macro_context(client) -> dict | None:
    """Use a cheap model with Google Search grounding to get live macro data."""
    try:
        resp = client.models.generate_content(
            model=_MODEL_FAST,
            contents=_MACRO_PROMPT,
            config=genai.types.GenerateContentConfig(
                tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        text = resp.text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        macro = json.loads(text)
        logger.info("Macro context fetched: Nifty=%s, RBI=%s%%",
                     macro.get('nifty50_level'), macro.get('rbi_repo_rate_pct'))
        return macro
    except Exception as e:
        logger.warning("Failed to fetch macro context via Google Search: %s", e)
        return None


def call_gemini(prompt_data: dict, group=None) -> GeminiResult:
    """Call Gemini with portfolio data and return structured insights.

    Step 1: Fetch live macro data via Google Search grounding (cheap model).
    Step 2: Run full portfolio analysis with structured output (main model).

    Args:
        prompt_data: Portfolio data dict from build_prompt_data.
        group: Optional AccountGroup for per-household AI config.
    """
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError('GEMINI_API_KEY environment variable is not set')

    model = _get_model()
    logger.info("Calling Gemini model: %s", model)

    client = genai.Client(api_key=api_key)

    # Step 1: fetch live macro context
    macro = _fetch_macro_context(client)
    if macro:
        prompt_data['macro_context'] = macro

    # Step 2: main analysis with structured output
    user_message = (
        "Analyze this portfolio. Use the data below and macro_context. "
        "Generate 8-15 insights across at least 5 categories.\n\n"
        f"Portfolio Data:\n{json.dumps(prompt_data, cls=_DecimalEncoder, indent=2)}"
    )

    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=genai.types.GenerateContentConfig(
            system_instruction=get_system_instruction(group),
            response_mime_type='application/json',
            response_schema=PortfolioInsightsResponse,
            temperature=0.3,
        ),
    )

    parsed = PortfolioInsightsResponse.model_validate_json(response.text)

    return GeminiResult(
        model=model,
        insights_dict=parsed.model_dump(mode='json'),
    )
