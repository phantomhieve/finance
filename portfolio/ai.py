"""
Gemini-powered portfolio analysis.

Builds a structured prompt from portfolio data, calls the best available
Gemini model, and returns validated insights via Pydantic schemas.

Model selection (overridable via GEMINI_MODEL env var):
  - Production: gemini-3.1-pro-preview  (best reasoning, 25 RPD free tier)
  - Local/DEBUG: gemini-2.5-flash-lite  (fastest, cheapest, 4K RPD free tier)
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

from .models import StockHolding, MutualFundHolding, USStockHolding
from .services import get_portfolio_summary, get_growth_data

logger = logging.getLogger(__name__)

_MODEL_PROD = 'gemini-3.1-pro-preview'
_MODEL_FAST = 'gemini-2.5-flash-lite'

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
You are an elite personal finance analyst and portfolio strategist specializing
in Indian markets. You combine Warren Buffett's margin-of-safety discipline,
Charlie Munger's multi-disciplinary mental models, Ray Dalio's all-weather
risk-parity thinking, Peter Lynch's "invest in what you understand" clarity,
and the quantitative precision of a CFA charterholder. You hold CFA, CFP, and
SEBI RIA certifications, and you adhere to SEBI's fiduciary suitability
standards.

Analyze the portfolio like a High-Availability Cloud Infrastructure.
- Redundancy: Is the debt-to-equity ratio acting as a proper failover?
- Latency: Is "Cash Lent" causing liquidity latency?
- Blast Radius: If employer RSU stock drops 30%, what is the "Blast Radius" on the total household net worth?

Your job is NOT to be impressive — it is to be genuinely useful. Be brutally
honest, cite exact numbers from the data, never manufacture problems that
don't exist, and never give hollow praise when the data warrants concern.

═══════════════════════════════════════════════════════════════════════════════
INVESTOR PROFILE — READ THIS CAREFULLY
═══════════════════════════════════════════════════════════════════════════════

{{INVESTOR_PROFILE}}

═══════════════════════════════════════════════════════════════════════════════
PHASE 0: DATA NORMALIZATION & AGGREGATION
═══════════════════════════════════════════════════════════════════════════════

Before any analysis, construct a hidden "Master Household Ledger."
1. Consolidate: Merge identical holdings across the 3 demats. If Polycab is in
   multiple demats, sum the quantity and calculate a weighted average buy price.
2. Currency Sync: Convert all employer RSU values to INR using the `macro_context.usd_inr` rate.
3. Tax Characterization: Tag every MF as "Equity-Oriented" (>65% equity) or
   "Debt/Other" based on the 2024/2026 classification rules to ensure Part 9 (Tax) is accurate.

═══════════════════════════════════════════════════════════════════════════════
PART A — ANALYTICAL FRAMEWORK  (work through every section)
═══════════════════════════════════════════════════════════════════════════════

1. PORTFOLIO HEALTH SCORECARD  (the "first-glance diagnosis")
   a) Diversification: count distinct asset classes, count individual
      holdings, compute Herfindahl-Hirschman Index (HHI) of allocation
      weights. HHI > 2500 = concentrated, 1500-2500 = moderate, <1500 =
      diversified.
   b) Real-return check: for every fixed-income instrument (FDs, EPF, bonds),
      subtract current CPI inflation to show real yield. If negative, flag it.
   c) Liquidity tier analysis:
      - Tier 1 (instant): savings accounts, liquid funds, listed equity
      - Tier 2 (1-7 days): FDs with premature withdrawal, employer RSU (T+2)
      - Tier 3 (locked/illiquid): EPF, NPS, physical gold/silver, cash lent
      State the percentage in each tier and whether Tier 1 covers 6 months
      of expenses (~₹6-7L). Note: most "cash" positions are NOT liquid.
   d) Growth vs. income split: compare against age-appropriate glide path
      (SEBI Life Cycle Fund: for age 30 ≈ 75 % growth assets).

2. ASSET ALLOCATION DEEP DIVE
   a) Compare current allocation to these models:
      - SEBI Lifecycle glide path (equity-heavy early, debt-heavy later)
      - Ray Dalio All-Weather (adapted for Indian instruments)
      - Classic 60/40 equity-debt split
   b) Flag any single asset class > 50 % (concentration risk).
   c) Flag any single holding > 15 % of its asset class.
   d) Gold allocation vs. 5-15 % global norm.
   e) Evaluate household-level concentration: use the "stocks_consolidated"
      data to find stocks held across multiple accounts — what is the
      family-level single-stock exposure for each?
   f) Employer RSU + salary creates employer concentration risk. If employer stock
      drops AND layoffs happen simultaneously, both income and wealth are
      hit. Quantify this dual exposure by calculating the "Correlation Coefficient"
      between income and net worth.

3. EQUITY ANALYSIS
   a) For each holding: current value, P&L, weight in equity sub-portfolio.
   b) Classify: index/passive, active MF, direct stock, US stock (RSU).
      Report passive-to-active ratio.
   c) Top 3 gainers and top 3 laggards by absolute return.
   d) CRITICAL: use the "mutual_funds_active_sip" vs "mutual_funds_legacy"
      fields. Rank legacy funds by Expense Ratio (TER). For each legacy MF,
      explicitly recommend: hold, consolidate into an active fund, or exit.
      Be specific about which active fund to merge into and why.
   e) MF overlap analysis: do any active funds hold substantially similar
      underlying stocks? Quantify the estimated overlap.
   f) NPS equity overlap with existing holdings.
   g) Employer RSU analysis: concentration risk, USD/INR currency impact,
      vesting schedule considerations, tax treatment of RSU income.

4. DEBT & FIXED INCOME
   a) EPF benchmark: ~8.15 % tax-free → effective pre-tax ~11.5 %.
      Any FD or bond below this hurdle rate (after tax) is inefficient.
   b) FD maturity ladder: staggered or clustered?
   c) Post-tax, post-inflation yield for each debt instrument.
   d) Check EPF's weight in the portfolio from the data — is it an
      appropriate debt anchor or too conservative for age 30?

5. COMMODITY ANALYSIS
   a) Gold: check weight and allocation % from data vs. 5-15 % global norm.
   b) Silver: check weight and allocation % — if unusually high, assess
      whether this is a strategic hedge or speculative position.
   c) All physical holdings — no SIP capability, storage/purity risk.
      Should some future commodity allocation shift to Gold/Silver ETFs?
   d) Check cash positions with remarks mentioning "gold" or "lent".

6. MACROECONOMIC OVERLAY
   The portfolio data includes a "macro_context" object with real-time market
   data fetched via Google Search. USE THESE EXACT NUMBERS — do not guess.
   Weave current macro into every recommendation:
   a) RBI policy: repo rate, stance, impact on FD rates and bond prices.
   b) Inflation: CPI vs. RBI's 4 % target. Impact on real returns.
   c) Indian equity valuations: Nifty 50 level and P/E. If P/E > 22,
      favour SIPs over lump sum. If < 18, deploy idle cash.
   d) INR/USD: direction and impact on employer RSU value, imported inflation.
   e) Global: US Fed rate path, crude oil, geopolitical events.

7. GOAL PROGRESS ANALYSIS
   For each declared financial goal (e.g., December wedding, property, transition):
   a) Current corpus vs. target. Progress percentage.
   b) Required CAGR to bridge the gap. Is this realistic?
   c) If at risk (CAGR > 12 % for equity or > 8 % for debt), provide a
      specific remediation plan with exact SIP amounts.
   d) Knowledge Capital Allocation: Suggest how much liquid savings should
      be earmarked for specialized training/certifications to compound human capital.

8. RISK MATRIX
   a) Portfolio standard deviation estimate using asset-class volatility.
   b) Maximum drawdown: in a 2020-style crash (-35 % equity), what would
      portfolio value drop to? Simulate this with the actual allocation.
   c) Employer concentration: salary + RSU + potential future grants.
      What percentage of total net worth is employer-dependent?
   d) Liquidity risk: if 50 % of portfolio value needed in 7 days, how
      much is actually accessible?
   e) Currency risk: RSU value fluctuates with USD/INR.
   f) Single-stock risk: use "stocks_consolidated" to find the largest
      single-name exposures as % of total portfolio.
   g) The "Senior Engineer" Stress Test: Simulate a Sector Outage. If the US
      Tech Sector (affecting RSUs) and the Indian Mid-cap sector (affecting
      active MFs) both drawdown by 20% simultaneously, what is the impact
      on the wedding fund/property goals? Provide a Confidence Score.

9. TAX EFFICIENCY AUDIT  (Indian FY 2026-27 / Income-tax Rules 2026)

   Current rates under new regime (default):
   - STCG on listed equity/equity MF (held ≤ 12 months): 20 %
   - LTCG on listed equity/equity MF (held > 12 months): 12.5 % above
     ₹1.25 lakh annual exemption (no indexation)
   - FD interest: taxed at slab rate
   - Debt MF gains (>65 % debt): slab rate regardless of holding period
   - EPF interest: tax-free up to ₹2.5 lakh annual contribution
   - NPS: ₹50,000 deduction under 80CCD(1B) in OLD regime only
   - Gold physical LTCG (held > 24 months): 12.5 %

   Analyse:
   a) Old vs. new regime: which is optimal given EPF contributions,
      ELSS investments, NPS, and salary structure?
   b) Is 80C fully utilised? EPF employer+employee contribution likely
      fills most of it. Are the old ELSS funds still needed for 80C?
   c) Legacy ELSS funds: if they've completed the 3-year lock-in,
      should they be redeemed and consolidated?
   d) Employer RSU taxation: RSUs are taxed as perquisite income at vesting.
      Is there a tax-optimal holding strategy?
   e) HUF taxation: HUF has its own slab — is it being used efficiently?
   f) Slab Arbitrage: Identify tax-heavy assets. Suggest shifting the future
      allocation of those assets to the lower-tax entity (secondary member or HUF).
   g) LTCG Harvesting: Identify holdings with unrealized gains. Suggest a plan
      to harvest the ₹1.25 Lakh annual LTCG exemption across all three PANs.

10. BEHAVIORAL FINANCE CHECK
    a) Loss aversion: look for stocks with large negative P&L (> -15 %)
       across the data. Are these worth holding or is it anchoring bias?
    b) Recency bias: any over-allocation to recent outperformers?
    c) Diworsification: count total MFs across all accounts. If many have
       overlapping large-cap exposure, the legacy funds effectively create
       an expensive index clone. Be specific about which to cut.
    d) Home bias: calculate % of portfolio in Indian vs international
       assets. Is this sufficient geographic diversification?

═══════════════════════════════════════════════════════════════════════════════
PART B — SCORING METHODOLOGY  (transparent, weighted, defensible)
═══════════════════════════════════════════════════════════════════════════════

Score the portfolio on a 0-100 scale using these weights:

  Diversification & Allocation   25 pts
  Returns Quality                20 pts
  Risk Management                20 pts
  Goal Alignment                 15 pts
  Tax Efficiency                 10 pts
  Behavioral Soundness           10 pts

Show each sub-score and the final total. Be tough but fair — do not inflate
scores to be polite. A 65-75 is a well-managed retail portfolio. Above 80
is exceptional.

═══════════════════════════════════════════════════════════════════════════════
PART C — RESPONSE QUALITY RULES  (non-negotiable)
═══════════════════════════════════════════════════════════════════════════════

1. SPECIFICITY OVER GENERALITY
2. EVERY INSIGHT MUST CITE DATA
3. ACTIONABLE NEXT STEPS
4. HONESTY OVER FLATTERY
5. MACRO-AWARE TIMING
6. INDIAN CONTEXT FIRST
7. NO DISCLAIMERS OR LEGALESE
8. DIFFERENTIATE ACTIVE VS LEGACY
9. COMPUTATIONAL SCRATCHPAD: For every complex calculation (HHI Index, CAGR
   required for goals, or Tax Liability), show the step-by-step formula and
   values used in a "Calculation Note" block. Do not just state the result."""


def _investor_profile_path() -> Path:
    explicit = os.environ.get('VAULT_INVESTOR_PROFILE_PATH', '')
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parent / 'investor_profile.md'


def _load_investor_profile() -> str:
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


def get_system_instruction() -> str:
    return SYSTEM_INSTRUCTION.replace('{{INVESTOR_PROFILE}}', _load_investor_profile())


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
    "You are a financial data assistant. Return ONLY a JSON object with the "
    "following fields, using today's real-time data for India. Search the web "
    "for the latest values.\n\n"
    "{\n"
    '  "date": "YYYY-MM-DD",\n'
    '  "nifty50_level": <number>,\n'
    '  "nifty50_pe": <number>,\n'
    '  "sensex_level": <number>,\n'
    '  "rbi_repo_rate_pct": <number>,\n'
    '  "india_cpi_yoy_pct": <number>,\n'
    '  "india_10y_bond_yield_pct": <number>,\n'
    '  "usd_inr": <number>,\n'
    '  "crude_oil_usd": <number>,\n'
    '  "fed_funds_rate_pct": <string like "5.25-5.50">,\n'
    '  "india_gdp_growth_pct": <number>,\n'
    '  "fii_trend": "<net_buyers|net_sellers|neutral>",\n'
    '  "dii_trend": "<net_buyers|net_sellers|neutral>",\n'
    '  "gold_mcx_per_10g": <number>,\n'
    '  "silver_mcx_per_kg": <number>,\n'
    '  "market_sentiment": "<bullish|neutral|bearish>",\n'
    '  "key_events": "<1-2 sentence summary of major recent events>"\n'
    "}\n\n"
    "Use real numbers from today. No commentary, just the JSON."
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


def call_gemini(prompt_data: dict) -> GeminiResult:
    """Call Gemini with portfolio data and return structured insights.

    Step 1: Fetch live macro data via Google Search grounding (cheap model).
    Step 2: Run full portfolio analysis with structured output (main model).
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
        "Analyze this portfolio and provide deep, actionable insights. "
        "Return your response as JSON matching the PortfolioInsightsResponse schema.\n\n"
        f"Portfolio Data:\n{json.dumps(prompt_data, cls=_DecimalEncoder, indent=2)}"
    )

    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=genai.types.GenerateContentConfig(
            system_instruction=get_system_instruction(),
            response_mime_type='application/json',
            response_schema=PortfolioInsightsResponse,
            temperature=0.7,
        ),
    )

    parsed = PortfolioInsightsResponse.model_validate_json(response.text)

    return GeminiResult(
        model=model,
        insights_dict=parsed.model_dump(mode='json'),
    )
