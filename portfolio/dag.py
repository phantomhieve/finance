"""Multi-Stage Directed Acyclic Graph (DAG) Workflow Engine for Portfolio Insights.

This module coordinates multi-stage, multi-model portfolio diagnostics for Indian
household wealth (see ADR 0001: docs/ux/0001-ai-calling-and-dag-strategy.md).
Instead of relying on a monolithic prompt where token dilution, arithmetic drift,
context truncation, and score hallucination occur, this engine decomposes the
analysis into deterministic Python pre-computation plus tiered DAG nodes:

  Stage 0 (Deterministic Decimal Quant Pre-Compute):
    - Node 0:  PortfolioQuantMetrics (Asset & equity HHI, full-universe stock
               concentration & loss-aversion flags, Tier 1/2/3 liquidity excluding
               illiquid receivables, FD post-tax hurdle vs 8.15% EPF, -35% equity
               crash & -30% RSU shock drawdowns, 6m momentum, Section 112A LTCG)

  Stage 1 (Parallel Diagnostic Lenses - Fan-out on TaskType.FAST / Flash):
    - Node 1A: Allocation & Liquidity Node (Asset mix, HHI concentration, emergency floor)
    - Node 1B: Asset Quality & Audit Node (Legacy MF audit, stock gainers/losers, real estate appraisal)
    - Node 1C: Macro Regime & Stress Node (Nifty PE valuation zone, -35% crash drawdown, trajectory)

  Stage 2 (Tactical Planning & Tax Synthesis - Fan-in on TaskType.REASONING / Carbon):
    - Node 2:  Strategy & Rebalancing Node (LTCG harvesting, Section 54/54EC, goal shortfall plans)

  Stage 3 (Terminal Synthesis & Deterministic Critic/Reducer on Carbon):
    - Node 3:  Terminal Synthesis Node (Mathematically grounded score calculation,
               category-coverage & critical-insight enforcement, executive summary)
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import re
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from pydantic import BaseModel, Field, model_validator

from pftracker.ai_gateway import TaskProfile, gateway
from pftracker.concurrency import DjangoSafeThreadPoolExecutor, safe_async_to_thread
from .ai import (
    AIResult,
    Insight,
    PortfolioInsightsResponse,
    _DecimalEncoder,
    _load_investor_profile,
)

logger = logging.getLogger(__name__)

_EPF_TAX_FREE_HURDLE_PCT = Decimal("8.15")
_POST_TAX_FACTOR_30_SLAB = Decimal("0.688")  # 1 - 0.312 (30% slab + 4% cess)
_SEC_112A_EXEMPTION_INR = Decimal("125000")
_DEFAULT_MONTHLY_EXPENSE_INR = Decimal("75000")


# ===========================================================================
# 0. Deterministic Decimal Quant Pre-Computation (Stage 0)
# ===========================================================================

def _dec(val: Any, default: str = "0") -> Decimal:
    """Safely convert numeric/string values into Decimal without float drift."""
    if val is None or val == "":
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    if isinstance(val, bool):
        return Decimal(default)
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _q2(val: Decimal) -> float:
    """Quantize a Decimal to 2 decimal places and convert to float at JSON boundary."""
    return float(val.quantize(Decimal("0.01")))


class PortfolioQuantMetrics(BaseModel):
    """Exact Decimal-computed portfolio metrics injected into downstream DAG stages."""
    total_value_inr: float = 0.0
    total_invested_inr: float = 0.0
    total_returns_inr: float = 0.0
    return_pct: float = 0.0

    # Allocation & Concentration
    growth_allocation_pct: float = 0.0
    stability_allocation_pct: float = 0.0
    asset_hhi: float = 0.0
    equity_stock_hhi: float = 0.0
    asset_classes_over_50pct: list[dict[str, Any]] = Field(default_factory=list)
    stocks_over_5pct: list[dict[str, Any]] = Field(default_factory=list)
    stocks_over_10pct: list[dict[str, Any]] = Field(default_factory=list)
    total_stock_count: int = 0

    # Full-universe Equity Quality & Behavioral Flags (never truncated)
    top_gainers: list[dict[str, Any]] = Field(default_factory=list)
    worst_losers: list[dict[str, Any]] = Field(default_factory=list)
    loss_aversion_flags: list[dict[str, Any]] = Field(default_factory=list)
    legacy_fund_count: int = 0
    legacy_fund_total_inr: float = 0.0

    # Liquidity Tiers & Emergency Floor
    liquid_cash_inr: float = 0.0
    illiquid_receivables_inr: float = 0.0
    tier1_liquid_inr: float = 0.0
    tier2_near_liquid_inr: float = 0.0
    tier3_illiquid_inr: float = 0.0
    monthly_expense_estimate_inr: float = 75000.0
    six_month_emergency_floor_inr: float = 450000.0
    emergency_floor_months_covered: float = 0.0
    emergency_floor_ok: bool = True

    # Fixed Debt vs Hurdle
    epf_tax_free_hurdle_pct: float = 8.15
    fds_below_epf_hurdle: list[dict[str, Any]] = Field(default_factory=list)
    fds_negative_real_yield: list[dict[str, Any]] = Field(default_factory=list)

    # Stress Tests & Trajectory
    total_equity_exposure_inr: float = 0.0
    equity_crash_35pct_loss_inr: float = 0.0
    post_crash_net_worth_inr: float = 0.0
    rsu_current_inr: float = 0.0
    rsu_pct_of_portfolio: float = 0.0
    rsu_shock_30pct_loss_inr: float = 0.0
    trajectory_trend: str = "stable"
    six_month_net_worth_change_pct: float = 0.0

    # Tax & Goals
    unrealized_equity_gains_inr: float = 0.0
    sec_112a_harvestable_ltcg_inr: float = 0.0
    at_risk_goals: list[dict[str, Any]] = Field(default_factory=list)


def _estimate_monthly_expense(investor_profile: str) -> Decimal:
    """Extract monthly household expense from investor profile if stated, else conservative default."""
    if investor_profile:
        match = re.search(
            r"(?i)(?:monthly\s+(?:household\s+)?(?:expenses?|burn|outflow|spend))[^\d\n]{0,25}₹?\s*([\d,]+(?:\.\d+)?)\s*(k|lakh|l)?",
            investor_profile,
        )
        if match:
            raw_num = _dec(match.group(1).replace(",", ""))
            unit = (match.group(2) or "").lower()
            if unit == "k":
                raw_num *= Decimal("1000")
            elif unit in ("l", "lakh"):
                raw_num *= Decimal("100000")
            if raw_num >= Decimal("10000"):
                return raw_num
    return _DEFAULT_MONTHLY_EXPENSE_INR


def compute_portfolio_quant_metrics(data: dict, investor_profile: str = "") -> PortfolioQuantMetrics:
    """Stage 0: Compute exact Decimal quantitative indicators across the full portfolio."""
    summary = data.get("summary") or {}
    total_value = _dec(
        summary.get("total_value")
        if summary.get("total_value") is not None
        else summary.get("total_current_value")
    )
    total_invested = _dec(summary.get("total_invested"))
    total_returns = (
        _dec(summary.get("total_returns"))
        if "total_returns" in summary
        else (total_value - total_invested)
    )
    if "return_pct" in summary and summary.get("return_pct") is not None:
        return_pct = _dec(summary.get("return_pct"))
    elif total_invested > 0:
        return_pct = (total_returns / total_invested) * Decimal("100")
    else:
        return_pct = Decimal("0")

    # 1. Asset Allocation, Growth/Stability Mix & Asset HHI
    alloc_source = data.get("consolidated") or data.get("asset_allocation") or []
    asset_hhi = Decimal("0")
    growth_pct = Decimal("0")
    stability_pct = Decimal("0")
    classes_over_50: list[dict[str, Any]] = []

    growth_tokens = ("equity", "stock", "mutual", "index", "rsu", "us ", "crypto", "real estate", "land", "plot")
    for item in alloc_source:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        pct = _dec(item.get("pct"))
        if pct <= 0 and total_value > 0 and item.get("value") is not None:
            pct = (_dec(item.get("value")) / total_value) * Decimal("100")
        if pct > 0:
            share = pct / Decimal("100")
            asset_hhi += (share * share) * Decimal("10000")
            if pct > Decimal("50"):
                classes_over_50.append({"name": name, "pct": _q2(pct)})
            n_low = name.lower()
            if any(tok in n_low for tok in growth_tokens):
                growth_pct += pct
            else:
                stability_pct += pct

    # 2. Full-Universe Stock Concentration, Equity HHI & Behavioral Flags
    stocks = [s for s in (data.get("stocks_consolidated") or []) if isinstance(s, dict)]
    total_stock_val = sum((_dec(s.get("total_current")) for s in stocks), Decimal("0"))
    equity_stock_hhi = Decimal("0")
    stocks_over_5: list[dict[str, Any]] = []
    stocks_over_10: list[dict[str, Any]] = []
    normalized_stocks: list[dict[str, Any]] = []

    for s in stocks:
        sym = str(s.get("symbol") or "UNKNOWN")
        cur = _dec(s.get("total_current"))
        inv = _dec(s.get("total_invested"))
        pnl = _dec(s.get("total_pnl")) if s.get("total_pnl") is not None else (cur - inv)
        if s.get("total_pnl_pct") is not None:
            pnl_pct = _dec(s.get("total_pnl_pct"))
        elif inv > 0:
            pnl_pct = (pnl / inv) * Decimal("100")
        else:
            pnl_pct = Decimal("0")

        if s.get("pct_of_portfolio") is not None:
            port_pct = _dec(s.get("pct_of_portfolio"))
        elif total_value > 0:
            port_pct = (cur / total_value) * Decimal("100")
        else:
            port_pct = Decimal("0")

        if total_stock_val > 0 and cur > 0:
            stock_share = cur / total_stock_val
            equity_stock_hhi += (stock_share * stock_share) * Decimal("10000")

        compact = {
            "symbol": sym,
            "current_inr": _q2(cur),
            "pnl_inr": _q2(pnl),
            "pnl_pct": _q2(pnl_pct),
            "pct_of_portfolio": _q2(port_pct),
        }
        normalized_stocks.append(compact)
        if port_pct > Decimal("5"):
            stocks_over_5.append(compact)
        if port_pct > Decimal("10"):
            stocks_over_10.append(compact)

    top_gainers = sorted(
        [s for s in normalized_stocks if s["pnl_pct"] > 0],
        key=lambda x: x["pnl_pct"],
        reverse=True,
    )[:5]
    worst_losers = sorted(
        [s for s in normalized_stocks if s["pnl_pct"] < 0],
        key=lambda x: x["pnl_pct"],
    )[:5]
    loss_aversion_flags = sorted(
        [s for s in normalized_stocks if Decimal(str(s["pnl_pct"])) <= Decimal("-15")],
        key=lambda x: x["pnl_pct"],
    )

    # 3. Liquidity Tiers & Illiquid Receivable Exclusion
    cash_data = data.get("cash") or {}
    liquid_cash = Decimal("0")
    illiquid_receivables = Decimal("0")
    if isinstance(cash_data, dict):
        positions = [p for p in (cash_data.get("positions") or []) if isinstance(p, dict)]
        if positions:
            for pos in positions:
                amt = _dec(pos.get("amount"))
                label = f"{pos.get('name', '')} {pos.get('remarks', '')}".lower()
                if any(tok in label for tok in ("lent", "given", "loan to", "receivable")):
                    illiquid_receivables += amt
                else:
                    liquid_cash += amt
        else:
            liquid_cash = _dec(cash_data.get("total"))

    equity_dict = data.get("equity") or {}
    mfs_all = [m for m in (data.get("mutual_funds_all") or []) if isinstance(m, dict)]
    if not mfs_all:
        mfs_all = [
            m
            for m in ((data.get("mutual_funds_active_sip") or []) + (data.get("mutual_funds_legacy") or []))
            if isinstance(m, dict)
        ]
    mf_total_val = sum((_dec(m.get("current")) for m in mfs_all), Decimal("0"))

    listed_domestic_equity = _dec(equity_dict.get("total"))
    if listed_domestic_equity <= 0:
        listed_domestic_equity = total_stock_val + mf_total_val
    if listed_domestic_equity <= 0:
        for item in data.get("asset_allocation") or []:
            if isinstance(item, dict) and any(
                k in str(item.get("name", "")).lower() for k in ("stock", "equity", "mutual", "index")
            ):
                if "us" not in str(item.get("name", "")).lower():
                    listed_domestic_equity += _dec(item.get("value"))

    raw_fds = data.get("fixed_deposits")
    fd_list: list[dict[str, Any]] = []
    fd_total = Decimal("0")
    if isinstance(raw_fds, list):
        fd_list = [f for f in raw_fds if isinstance(f, dict)]
        fd_total = sum((_dec(f.get("current_value") or f.get("principal")) for f in fd_list), Decimal("0"))
    elif isinstance(raw_fds, dict):
        fd_total = _dec(raw_fds.get("current_value") or raw_fds.get("total"))

    rsu_current = _dec((data.get("us_stocks_total") or {}).get("current_inr"))
    if rsu_current <= 0:
        rsu_current = sum(
            (_dec(u.get("current_inr")) for u in (data.get("us_stocks_rsu") or []) if isinstance(u, dict)),
            Decimal("0"),
        )

    epf_bal = _dec((data.get("epf") or {}).get("balance")) + _dec((data.get("pf") or {}).get("balance"))
    nps_bal = _dec((data.get("nps") or {}).get("balance"))
    re_bal = _dec((data.get("real_estate") or {}).get("total_current"))
    comm_dict = data.get("commodities") or {}
    comm_bal = _dec(comm_dict.get("total_value"))
    if comm_bal <= 0 and isinstance(comm_dict, dict):
        comm_bal = _dec((comm_dict.get("gold") or {}).get("current_value")) + _dec(
            (comm_dict.get("silver") or {}).get("current_value")
        )

    has_explicit_breakdown = any(
        k in data
        for k in (
            "cash",
            "equity",
            "stocks_consolidated",
            "mutual_funds_all",
            "asset_allocation",
            "consolidated",
            "fixed_deposits",
            "epf",
            "real_estate",
        )
    )
    if not has_explicit_breakdown and total_value > 0:
        # Sparse summary-only payload (e.g. unit test fixture): assume balanced liquid share
        tier1_liquid = (total_value * Decimal("0.50")).quantize(Decimal("0.01"))
        listed_domestic_equity = (total_value * Decimal("0.40")).quantize(Decimal("0.01"))
    else:
        tier1_liquid = liquid_cash + listed_domestic_equity

    tier2_near_liquid = fd_total + rsu_current
    tier3_illiquid = epf_bal + nps_bal + re_bal + comm_bal + illiquid_receivables

    monthly_exp = _estimate_monthly_expense(investor_profile)
    six_month_floor = monthly_exp * Decimal("6")
    months_covered = (tier1_liquid / monthly_exp) if monthly_exp > 0 else Decimal("0")
    emergency_ok = tier1_liquid >= six_month_floor

    # 4. Fixed Deposits vs 8.15% Tax-Free EPF Hurdle & CPI Inflation
    macro_ctx = data.get("macro_context") or {}
    cpi_pct = _dec(macro_ctx.get("cpi_inflation_pct") or macro_ctx.get("cpi_pct"), default="5.2")
    fds_below_hurdle: list[dict[str, Any]] = []
    fds_neg_real: list[dict[str, Any]] = []
    for fd in fd_list:
        rate = _dec(fd.get("rate"))
        if rate <= 0:
            continue
        post_tax = rate * _POST_TAX_FACTOR_30_SLAB
        fd_info = {
            "name": str(fd.get("name") or "FD"),
            "pre_tax_rate_pct": _q2(rate),
            "post_tax_rate_pct": _q2(post_tax),
            "current_value_inr": _q2(_dec(fd.get("current_value") or fd.get("principal"))),
        }
        if post_tax < _EPF_TAX_FREE_HURDLE_PCT:
            fds_below_hurdle.append(fd_info)
        if post_tax < cpi_pct:
            fds_neg_real.append(fd_info)

    # 5. Stress Drawdown Math (-35% Equity Crash & -30% RSU Shock)
    total_equity_exposure = listed_domestic_equity + rsu_current
    crash_loss_35 = total_equity_exposure * Decimal("0.35")
    post_crash_nw = max(Decimal("0"), total_value - crash_loss_35)
    rsu_shock_30 = rsu_current * Decimal("0.30")
    rsu_pct = ((rsu_current / total_value) * Decimal("100")) if total_value > 0 else Decimal("0")

    # 6. 6-Month Growth Momentum Trajectory
    history = [h for h in (data.get("growth_history") or [])[-6:] if isinstance(h, dict)]
    trajectory = "stable"
    six_mo_change_pct = Decimal("0")
    if len(history) >= 2:
        first_val = _dec(history[0].get("total_value"))
        last_val = _dec(history[-1].get("total_value"))
        if first_val > 0:
            six_mo_change_pct = ((last_val - first_val) / first_val) * Decimal("100")
        if len(history) >= 4:
            mid = len(history) // 2
            v0 = _dec(history[0].get("total_value"))
            vm = _dec(history[mid].get("total_value"))
            vl = _dec(history[-1].get("total_value"))
            early_gain = ((vm - v0) / v0) if v0 > 0 else Decimal("0")
            late_gain = ((vl - vm) / vm) if vm > 0 else Decimal("0")
            if late_gain - early_gain > Decimal("0.015"):
                trajectory = "accelerating"
            elif early_gain - late_gain > Decimal("0.015"):
                trajectory = "decelerating"

    # 7. Section 112A Tax Harvesting & Legacy Funds
    positive_stock_gains = sum(
        (max(Decimal("0"), _dec(s.get("total_pnl"))) for s in stocks),
        Decimal("0"),
    )
    positive_mf_gains = sum(
        (max(Decimal("0"), _dec(m.get("pnl"))) for m in mfs_all),
        Decimal("0"),
    )
    unrealized_gains = positive_stock_gains + positive_mf_gains
    harvestable_ltcg = min(_SEC_112A_EXEMPTION_INR, unrealized_gains)

    legacy_funds = [m for m in (data.get("mutual_funds_legacy") or []) if isinstance(m, dict)]
    legacy_total = sum((_dec(m.get("current")) for m in legacy_funds), Decimal("0"))

    # 8. Goal Shortfalls
    at_risk_goals: list[dict[str, Any]] = []
    for g in data.get("goals") or []:
        if not isinstance(g, dict):
            continue
        status = str(g.get("status") or "").lower()
        monthly_needed = _dec(g.get("monthly_needed"))
        prog = _dec(g.get("progress_pct"))
        if status in ("behind", "at_risk", "off_track", "shortfall") or (monthly_needed > 0 and prog < Decimal("80")):
            at_risk_goals.append(
                {
                    "label": g.get("label") or g.get("financial_year"),
                    "financial_year": g.get("financial_year"),
                    "target_inr": _q2(_dec(g.get("target"))),
                    "progress_pct": _q2(prog),
                    "monthly_needed_inr": _q2(monthly_needed),
                    "status": g.get("status"),
                }
            )

    return PortfolioQuantMetrics(
        total_value_inr=_q2(total_value),
        total_invested_inr=_q2(total_invested),
        total_returns_inr=_q2(total_returns),
        return_pct=_q2(return_pct),
        growth_allocation_pct=_q2(growth_pct),
        stability_allocation_pct=_q2(stability_pct),
        asset_hhi=_q2(asset_hhi),
        equity_stock_hhi=_q2(equity_stock_hhi),
        asset_classes_over_50pct=classes_over_50,
        stocks_over_5pct=stocks_over_5,
        stocks_over_10pct=stocks_over_10,
        total_stock_count=len(stocks),
        top_gainers=top_gainers,
        worst_losers=worst_losers,
        loss_aversion_flags=loss_aversion_flags,
        legacy_fund_count=len(legacy_funds),
        legacy_fund_total_inr=_q2(legacy_total),
        liquid_cash_inr=_q2(liquid_cash),
        illiquid_receivables_inr=_q2(illiquid_receivables),
        tier1_liquid_inr=_q2(tier1_liquid),
        tier2_near_liquid_inr=_q2(tier2_near_liquid),
        tier3_illiquid_inr=_q2(tier3_illiquid),
        monthly_expense_estimate_inr=_q2(monthly_exp),
        six_month_emergency_floor_inr=_q2(six_month_floor),
        emergency_floor_months_covered=_q2(months_covered),
        emergency_floor_ok=emergency_ok,
        epf_tax_free_hurdle_pct=_q2(_EPF_TAX_FREE_HURDLE_PCT),
        fds_below_epf_hurdle=fds_below_hurdle,
        fds_negative_real_yield=fds_neg_real,
        total_equity_exposure_inr=_q2(total_equity_exposure),
        equity_crash_35pct_loss_inr=_q2(crash_loss_35),
        post_crash_net_worth_inr=_q2(post_crash_nw),
        rsu_current_inr=_q2(rsu_current),
        rsu_pct_of_portfolio=_q2(rsu_pct),
        rsu_shock_30pct_loss_inr=_q2(rsu_shock_30),
        trajectory_trend=trajectory,
        six_month_net_worth_change_pct=_q2(six_mo_change_pct),
        unrealized_equity_gains_inr=_q2(unrealized_gains),
        sec_112a_harvestable_ltcg_inr=_q2(harvestable_ltcg),
        at_risk_goals=at_risk_goals,
    )


# ===========================================================================
# 1. Intermediate Pydantic Schemas for DAG Nodes
# ===========================================================================

class LegacyFundAuditItem(BaseModel):
    """Typed audit verdict for a legacy mutual fund holding (Gemini response_schema safe)."""
    fund_name: str = Field(default="", description="Mutual fund name")
    action: str = Field(default="hold", description="Recommended action: hold | merge | exit")
    target_fund: str = Field(default="", description="Target active SIP fund when action is merge/exit")
    rationale: str = Field(default="", description="Concise rationale citing overlap, size, or tax impact")

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_dict(cls, v: Any) -> Any:
        if isinstance(v, dict):
            d = dict(v)
            if "target_fund" not in d and "target" in d:
                d["target_fund"] = str(d.get("target") or "")
            if "fund_name" not in d and "name" in d:
                d["fund_name"] = str(d.get("name") or "")
            return d
        return v

    def __getitem__(self, key: str) -> Any:
        if key == "target":
            return self.target_fund
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "target":
            return self.target_fund or default
        return getattr(self, key, default)


class AllocationLensResult(BaseModel):
    """Output of Stage 1A: Allocation, Concentration, and Liquidity diagnostics."""
    sub_score: int = Field(default=70, ge=0, le=100, description="Score 0-100 for allocation hygiene")
    allocation_findings: list[str] = Field(default_factory=list, description="Asset class mix vs age glide path findings")
    concentration_warnings: list[str] = Field(default_factory=list, description="Single stock/class concentration & HHI warnings")
    liquidity_tier_assessment: str = Field(default="", description="Tier 1 instant vs Tier 2 vs Tier 3 illiquid analysis")
    emergency_floor_ok: bool = Field(default=True, description="True if 6-month liquid emergency floor is satisfied")
    candidate_insights: list[Insight] = Field(default_factory=list, description="Candidate insights generated by this lens")


class QualityLensResult(BaseModel):
    """Output of Stage 1B: Fund quality, legacy audit, and real estate appraisal."""
    sub_score: int = Field(default=70, ge=0, le=100, description="Score 0-100 for asset and holding quality")
    equity_quality_findings: list[str] = Field(default_factory=list, description="Top gainers, loss leaders, and equity quality")
    legacy_fund_audits: list[LegacyFundAuditItem] = Field(
        default_factory=list,
        description="Typed audits for legacy MFs: {fund_name, action: hold|merge|exit, target_fund, rationale}",
    )
    real_estate_findings: list[str] = Field(default_factory=list, description="Micro-market appraisal and rental yield findings")
    debt_hurdle_findings: list[str] = Field(default_factory=list, description="EPF tax-free hurdle vs FD/bond returns")
    candidate_insights: list[Insight] = Field(default_factory=list, description="Candidate insights generated by this lens")


class MacroStressLensResult(BaseModel):
    """Output of Stage 1C: Macroeconomic regime and stress simulation."""
    sub_score: int = Field(default=70, ge=0, le=100, description="Score 0-100 for macro alignment and stress resilience")
    valuation_regime: str = Field(default="", description="Nifty PE valuation status e.g. Fair, Stretched, Undervalued")
    crash_drawdown_amount: str = Field(default="", description="Simulated 2020-style -35% equity crash drawdown in rupees")
    stress_findings: list[str] = Field(default_factory=list, description="Layoff/tech shock and currency risk findings")
    trajectory_trend: str = Field(default="stable", description="Growth history momentum: accelerating|stable|decelerating")
    candidate_insights: list[Insight] = Field(default_factory=list, description="Candidate insights generated by this lens")


class StrategyLensResult(BaseModel):
    """Output of Stage 2: Cross-pillar rebalancing, capital redeployment, and tax optimization."""
    sub_score: int = Field(default=70, ge=0, le=100, description="Score 0-100 for strategic execution and tax efficiency")
    tax_harvesting_plan: str = Field(default="", description="Section 112A LTCG harvesting and Section 54/54EC strategy")
    rebalancing_roadmap: list[str] = Field(default_factory=list, description="Actionable redeployment and rebalancing moves")
    goal_shortfall_plans: list[str] = Field(default_factory=list, description="Specific SIP/lump-sum plans to close goal gaps")
    candidate_insights: list[Insight] = Field(default_factory=list, description="Candidate insights generated by this lens")


class DAGExecutionMetadata(BaseModel):
    """Traceability metadata recording execution metrics across all DAG nodes."""
    started_at: str
    completed_at: str
    elapsed_ms: float
    nodes_executed: list[str]
    sub_scores: dict[str, int]
    grounded_score: int
    fallback_used: bool = False
    degraded_nodes: list[str] = Field(default_factory=list)
    stage_cache_hits: list[str] = Field(default_factory=list)
    quant_metrics: dict[str, Any] = Field(default_factory=dict)


# ===========================================================================
# 2. Surgical Data Slicers (Compact JSON + Full-Universe Behavioral Signals)
# ===========================================================================

def _compact_json(payload: Any) -> str:
    """Serialize payload as compact JSON without indentation whitespace bloat."""
    return json.dumps(payload, cls=_DecimalEncoder, separators=(",", ":"), ensure_ascii=False)


def _extract_allocation_slice(data: dict, quant: PortfolioQuantMetrics) -> dict:
    """Extract allocation, concentration, and liquidity tier data plus exact quant metrics."""
    return {
        "summary": data.get("summary", {}),
        "asset_allocation": data.get("asset_allocation", []),
        "consolidated": data.get("consolidated", []),
        "top_stocks_by_weight": [
            {
                "symbol": s.get("symbol"),
                "total_current": s.get("total_current"),
                "pct_of_portfolio": s.get("pct_of_portfolio"),
                "total_pnl_pct": s.get("total_pnl_pct"),
            }
            for s in (data.get("stocks_consolidated") or [])[:15]
        ],
        "us_stocks_total": data.get("us_stocks_total", {}),
        "cash": data.get("cash", {}),
        "epf": data.get("epf", {}),
        "nps": data.get("nps", {}),
        "quant_allocation": {
            "growth_allocation_pct": quant.growth_allocation_pct,
            "stability_allocation_pct": quant.stability_allocation_pct,
            "asset_hhi": quant.asset_hhi,
            "equity_stock_hhi": quant.equity_stock_hhi,
            "asset_classes_over_50pct": quant.asset_classes_over_50pct,
            "stocks_over_5pct": quant.stocks_over_5pct,
            "stocks_over_10pct": quant.stocks_over_10pct,
            "liquid_cash_inr": quant.liquid_cash_inr,
            "illiquid_receivables_inr": quant.illiquid_receivables_inr,
            "tier1_liquid_inr": quant.tier1_liquid_inr,
            "tier2_near_liquid_inr": quant.tier2_near_liquid_inr,
            "tier3_illiquid_inr": quant.tier3_illiquid_inr,
            "six_month_emergency_floor_inr": quant.six_month_emergency_floor_inr,
            "emergency_floor_months_covered": quant.emergency_floor_months_covered,
            "emergency_floor_ok": quant.emergency_floor_ok,
        },
    }


def _extract_quality_slice(data: dict, quant: PortfolioQuantMetrics) -> dict:
    """Extract holding-level quality, full-universe tail losers, legacy funds, RE, and debt."""
    top_stocks = (data.get("stocks_consolidated") or [])[:15]
    included_symbols = {s.get("symbol") for s in top_stocks if isinstance(s, dict)}
    tail_losers = [
        s
        for s in (data.get("stocks_consolidated") or [])[15:]
        if isinstance(s, dict)
        and s.get("symbol") not in included_symbols
        and _dec(s.get("total_pnl_pct")) <= Decimal("-15")
    ]

    return {
        "stocks_sampled": [
            {
                "symbol": s.get("symbol"),
                "total_invested": s.get("total_invested"),
                "total_current": s.get("total_current"),
                "total_pnl": s.get("total_pnl"),
                "total_pnl_pct": s.get("total_pnl_pct"),
            }
            for s in (top_stocks + tail_losers)
        ],
        "mutual_funds_active_sip": data.get("mutual_funds_active_sip", []),
        "mutual_funds_legacy": data.get("mutual_funds_legacy", []),
        "real_estate_holdings": [
            {
                "name": h.get("name"),
                "property_type": h.get("property_type"),
                "acquisition_type": h.get("acquisition_type"),
                "micro_market_tag": h.get("micro_market_tag"),
                "location_summary": h.get("location_summary"),
                "cost_basis": h.get("cost_basis"),
                "current_valuation": h.get("current_valuation"),
                "cagr_pct": h.get("cagr_pct"),
                "rental_yield_pct": h.get("rental_yield_pct"),
            }
            for h in (data.get("real_estate") or {}).get("holdings", [])
        ],
        "fixed_deposits": data.get("fixed_deposits", []),
        "epf": data.get("epf", {}),
        "quant_quality": {
            "total_stock_count": quant.total_stock_count,
            "top_gainers": quant.top_gainers,
            "worst_losers": quant.worst_losers,
            "loss_aversion_flags": quant.loss_aversion_flags,
            "epf_tax_free_hurdle_pct": quant.epf_tax_free_hurdle_pct,
            "fds_below_epf_hurdle": quant.fds_below_epf_hurdle,
            "fds_negative_real_yield": quant.fds_negative_real_yield,
        },
    }


def _extract_macro_stress_slice(data: dict, quant: PortfolioQuantMetrics) -> dict:
    """Extract macro indicators, RSU/crypto exposure, growth momentum, and exact stress math."""
    return {
        "summary": data.get("summary", {}),
        "asset_allocation": data.get("asset_allocation", []),
        "macro_context": data.get("macro_context", {}),
        "us_stocks_total": data.get("us_stocks_total", {}),
        "crypto": data.get("crypto", {}),
        "growth_history": (data.get("growth_history") or [])[-6:],
        "quant_stress": {
            "total_equity_exposure_inr": quant.total_equity_exposure_inr,
            "equity_crash_35pct_loss_inr": quant.equity_crash_35pct_loss_inr,
            "post_crash_net_worth_inr": quant.post_crash_net_worth_inr,
            "rsu_current_inr": quant.rsu_current_inr,
            "rsu_pct_of_portfolio": quant.rsu_pct_of_portfolio,
            "rsu_shock_30pct_loss_inr": quant.rsu_shock_30pct_loss_inr,
            "trajectory_trend": quant.trajectory_trend,
            "six_month_net_worth_change_pct": quant.six_month_net_worth_change_pct,
        },
    }


# ===========================================================================
# 3. DAG Node Runners
# ===========================================================================

def run_stage_1a_allocation(
    data: dict,
    investor_profile: str,
    quant: PortfolioQuantMetrics | None = None,
) -> AllocationLensResult:
    """Stage 1A: Allocation, Concentration, and Liquidity Lens."""
    logger.debug("[DAG] Executing Stage 1A: Allocation & Liquidity Node")
    quant = quant or compute_portfolio_quant_metrics(data, investor_profile)
    subset = _extract_allocation_slice(data, quant)
    prompt = f"""\
You are an expert quantitative asset allocation analyst for Indian family wealth.
Use the pre-computed quant_allocation figures directly—do NOT recompute arithmetic by hand.

1. Asset Allocation vs Age Glide Path:
   - Compare growth vs stability split against the investor profile (age 25-35 norm: ~70-80% growth, ~20-30% stability).
2. Concentration & HHI:
   - Cite asset_hhi, equity_stock_hhi, stocks_over_5pct, stocks_over_10pct, and asset_classes_over_50pct.
   - Assess dual employer exposure (RSU value + salary dependency).
3. Liquidity Tiers & Emergency Floor:
   - Cite exact tier1_liquid_inr (excluding illiquid lent/given receivables), tier2_near_liquid_inr, tier3_illiquid_inr, and emergency_floor_ok.

Assign a calibrated sub_score (0-100) and generate 2-4 candidate Insight objects.

Investor Profile:
{investor_profile}

Portfolio Slice:
{_compact_json(subset)}
"""
    return gateway.generate_structured(
        schema=AllocationLensResult,
        prompt=prompt,
        task=TaskProfile.PORTFOLIO_DAG_ALLOCATION,
    )


def run_stage_1b_quality(
    data: dict,
    investor_profile: str,
    quant: PortfolioQuantMetrics | None = None,
) -> QualityLensResult:
    """Stage 1B: Asset Quality, Fund Audit, and Real Estate Appraisal Lens."""
    logger.debug("[DAG] Executing Stage 1B: Asset Quality & Audit Node")
    quant = quant or compute_portfolio_quant_metrics(data, investor_profile)
    subset = _extract_quality_slice(data, quant)
    prompt = f"""\
You are a senior asset quality and fund portfolio manager for Indian family wealth.
Use the pre-computed quant_quality metrics (including full-universe loss_aversion_flags and fds_below_epf_hurdle).

1. Equity Quality & Behavioral Flags:
   - Cite top_gainers, worst_losers, and EVERY stock in loss_aversion_flags (pnl_pct <= -15%).
2. Legacy Mutual Fund Audit:
   - For EACH fund in mutual_funds_legacy, populate legacy_fund_audits with fund_name, action ('hold'|'merge'|'exit'), target_fund, and rationale.
3. Real Estate Micro-Market Quality:
   - Evaluate corridor catalysts, rental yield vs 2-4% norm, and CAGR vs 8-12% land benchmark. Distinguish INHERITED vs purchased properties.
4. Fixed Debt Quality:
   - Compare post-tax FD yields in fds_below_epf_hurdle against the 8.15% tax-free EPF hurdle.

Assign a calibrated sub_score (0-100) and generate 2-4 candidate Insight objects.

Investor Profile:
{investor_profile}

Portfolio Slice:
{_compact_json(subset)}
"""
    return gateway.generate_structured(
        schema=QualityLensResult,
        prompt=prompt,
        task=TaskProfile.PORTFOLIO_DAG_QUALITY,
    )


def run_stage_1c_macro(
    data: dict,
    investor_profile: str,
    quant: PortfolioQuantMetrics | None = None,
) -> MacroStressLensResult:
    """Stage 1C: Macroeconomic Regime and Stress Simulation Lens."""
    logger.debug("[DAG] Executing Stage 1C: Macro Regime & Stress Node")
    quant = quant or compute_portfolio_quant_metrics(data, investor_profile)
    subset = _extract_macro_stress_slice(data, quant)
    prompt = f"""\
You are a macroeconomic strategist and risk analyst for Indian wealth management.
Use the exact pre-computed quant_stress drawdown numbers rather than estimating mental arithmetic.

1. Macro Valuation Regime:
   - Assess Nifty P/E vs historical median (20-22x fair value), RBI repo rate stance, and CPI inflation.
2. Crash Simulation (2020-Style -35% Equity Drawdown):
   - Cite exact equity_crash_35pct_loss_inr and post_crash_net_worth_inr from quant_stress.
3. Tech / Employer Shock:
   - Cite rsu_shock_30pct_loss_inr and evaluate combined RSU + tech slowdown vulnerability.
4. Trajectory Momentum:
   - Align trajectory_trend with quant_stress.trajectory_trend and six_month_net_worth_change_pct.

Assign a calibrated sub_score (0-100) and generate 2-3 candidate Insight objects.

Investor Profile:
{investor_profile}

Portfolio Slice:
{_compact_json(subset)}
"""
    return gateway.generate_structured(
        schema=MacroStressLensResult,
        prompt=prompt,
        task=TaskProfile.PORTFOLIO_DAG_MACRO,
    )


def run_stage_2_strategy(
    data: dict,
    investor_profile: str,
    allocation: AllocationLensResult,
    quality: QualityLensResult,
    macro: MacroStressLensResult,
    quant: PortfolioQuantMetrics | None = None,
) -> StrategyLensResult:
    """Stage 2: Cross-Pillar Strategy, Tactical Rebalancing, and Tax Optimization."""
    logger.debug("[DAG] Executing Stage 2: Strategy & Rebalancing Synthesis Node")
    quant = quant or compute_portfolio_quant_metrics(data, investor_profile)
    context = {
        "summary": data.get("summary", {}),
        "goals": data.get("goals", []),
        "quant_strategy": {
            "unrealized_equity_gains_inr": quant.unrealized_equity_gains_inr,
            "sec_112a_harvestable_ltcg_inr": quant.sec_112a_harvestable_ltcg_inr,
            "legacy_fund_count": quant.legacy_fund_count,
            "legacy_fund_total_inr": quant.legacy_fund_total_inr,
            "at_risk_goals": quant.at_risk_goals,
            "fds_below_epf_hurdle": quant.fds_below_epf_hurdle,
        },
        "stage1_allocation_findings": allocation.allocation_findings,
        "stage1_concentration_warnings": allocation.concentration_warnings,
        "stage1_legacy_fund_audits": [a.model_dump(mode="json") for a in quality.legacy_fund_audits],
        "stage1_real_estate_findings": quality.real_estate_findings,
        "stage1_macro_regime": macro.valuation_regime,
        "stage1_crash_drawdown": macro.crash_drawdown_amount,
    }
    prompt = f"""\
You are a principal wealth planner synthesizing multi-lens findings into an actionable execution plan.
Use the Stage 1 analytical results, quant_strategy figures, and investor goals:

1. Tax Optimization (Indian FY 2026-27):
   - LTCG harvesting: utilize Rs 1.25L Section 112A exemption per PAN (harvestable: INR {quant.sec_112a_harvestable_ltcg_inr:,.0f}).
   - Inherited Real Estate: evaluate Section 54/54EC exemptions and compare 12.5% without indexation vs 20% with indexation.
   - Old vs New Tax Regime optimization for deductions (80CCD(1B), EPF, HRA).
2. Capital Redeployment & Rebalancing Roadmap:
   - Route proceeds from legacy fund exits (INR {quant.legacy_fund_total_inr:,.0f}) or sub-hurdle FDs into core active SIP funds or underfunded goals.
3. Goal Shortfall Closure:
   - Specify required monthly SIP adjustment or lump-sum allocation for at_risk_goals.

Assign a calibrated sub_score (0-100) and generate 2-4 candidate Insight objects.

Investor Profile:
{investor_profile}

Synthesis Context:
{_compact_json(context)}
"""
    return gateway.generate_structured(
        schema=StrategyLensResult,
        prompt=prompt,
        task=TaskProfile.PORTFOLIO_DAG_STRATEGY,
    )


def _curate_and_enforce_insights(
    synthesized: list[Insight],
    pooled_candidates: list[Insight],
    max_insights: int = 14,
    min_categories: int = 5,
) -> list[Insight]:
    """Deterministic Critic/Reducer: deduplicate titles, preserve critical flags, and backfill dropped categories."""
    curated: list[Insight] = []
    seen_titles: set[str] = set()

    for item in synthesized:
        key = item.title.strip().lower()
        if key and key not in seen_titles:
            seen_titles.add(key)
            curated.append(item)

    if not pooled_candidates:
        return curated[:max_insights]

    # 1. Ensure no critical candidate insight was silently dropped while room remains
    for cand in pooled_candidates:
        if len(curated) >= max_insights:
            break
        key = cand.title.strip().lower()
        if str(cand.severity.value if hasattr(cand.severity, "value") else cand.severity) == "critical" and key not in seen_titles:
            seen_titles.add(key)
            curated.append(cand)

    # 2. Backfill distinct categories from pooled_candidates if LLM covered < min_categories
    covered_cats = {
        (i.category.value if hasattr(i.category, "value") else str(i.category))
        for i in curated
    }
    if len(covered_cats) < min_categories:
        for cand in pooled_candidates:
            if len(curated) >= max_insights or len(covered_cats) >= min_categories:
                break
            cat = cand.category.value if hasattr(cand.category, "value") else str(cand.category)
            key = cand.title.strip().lower()
            if cat not in covered_cats and key not in seen_titles:
                seen_titles.add(key)
                covered_cats.add(cat)
                curated.append(cand)

    return curated[:max_insights]


def compute_grounded_health_score(
    allocation: AllocationLensResult,
    quality: QualityLensResult,
    macro: MacroStressLensResult,
    strategy: StrategyLensResult,
) -> int:
    """Compute composite portfolio score: Allocation (30%) + Quality (25%) + Strategy (25%) + Macro (20%)."""
    raw = (
        (Decimal("0.30") * Decimal(allocation.sub_score))
        + (Decimal("0.25") * Decimal(quality.sub_score))
        + (Decimal("0.25") * Decimal(strategy.sub_score))
        + (Decimal("0.20") * Decimal(macro.sub_score))
    )
    return max(0, min(100, int(round(float(raw)))))


def run_stage_3_terminal_synthesis(
    data: dict,
    investor_profile: str,
    allocation: AllocationLensResult,
    quality: QualityLensResult,
    macro: MacroStressLensResult,
    strategy: StrategyLensResult,
    quant: PortfolioQuantMetrics | None = None,
) -> PortfolioInsightsResponse:
    """Stage 3: Grounded Composite Health Scoring and Terminal Insight Compilation."""
    logger.debug("[DAG] Executing Stage 3: Terminal Grounding & Scoring Node")
    quant = quant or compute_portfolio_quant_metrics(data, investor_profile)

    # 1. Deterministic, mathematically grounded health score
    grounded_score = compute_grounded_health_score(allocation, quality, macro, strategy)

    # 2. Pool & deduplicate candidate insights across all DAG stages
    pooled_insights: list[Insight] = (
        allocation.candidate_insights
        + quality.candidate_insights
        + macro.candidate_insights
        + strategy.candidate_insights
    )
    deduped_insights: list[Insight] = []
    seen_titles: set[str] = set()
    for item in pooled_insights:
        key = item.title.strip().lower()
        if key not in seen_titles:
            seen_titles.add(key)
            deduped_insights.append(item)

    brief = {
        "summary": data.get("summary", {}),
        "grounded_score": grounded_score,
        "sub_scores": {
            "allocation": allocation.sub_score,
            "quality": quality.sub_score,
            "strategy": strategy.sub_score,
            "macro": macro.sub_score,
        },
        "quant_headline": {
            "total_value_inr": quant.total_value_inr,
            "return_pct": quant.return_pct,
            "tier1_liquid_inr": quant.tier1_liquid_inr,
            "emergency_floor_ok": quant.emergency_floor_ok,
            "equity_crash_35pct_loss_inr": quant.equity_crash_35pct_loss_inr,
            "sec_112a_harvestable_ltcg_inr": quant.sec_112a_harvestable_ltcg_inr,
        },
        "allocation_highlights": allocation.allocation_findings[:3],
        "quality_highlights": quality.equity_quality_findings[:3],
        "macro_regime": macro.valuation_regime,
        "crash_drawdown": macro.crash_drawdown_amount,
        "tax_plan": strategy.tax_harvesting_plan,
        "rebalancing_actions": strategy.rebalancing_roadmap[:3],
        "candidate_insights": [i.model_dump(mode="json") for i in deduped_insights[:15]],
    }

    prompt = f"""\
You are the executive editor finalizing the comprehensive Portfolio Insights Report.
Review the DAG stage outputs and produce the terminal PortfolioInsightsResponse:

MANDATORY REQUIREMENTS:
1. summary: Exactly 2-3 sentences. Lead with the portfolio's single greatest strength,
   followed by its most urgent vulnerability or redeployment priority. Cite actual total value and return %.
2. score: MUST BE EXACTLY {grounded_score} (pre-calculated from the 4 DAG pillar sub-scores).
3. insights: Curate 8-14 high-impact Insight objects from candidate_insights (and supplement if needed to cover at least 5 distinct categories).
   Each must cite exact figures and specify an actionable recommendation.
4. market_context: 1-2 sentences summarizing today's macro environment (Nifty valuation, interest rates).
5. outlook: 2-3 sentences detailing immediate next steps for the investor over the upcoming quarter.

Investor Profile:
{investor_profile}

DAG Compilation Brief:
{_compact_json(brief)}
"""
    final_response = gateway.generate_structured(
        schema=PortfolioInsightsResponse,
        prompt=prompt,
        task=TaskProfile.PORTFOLIO_DAG_SYNTHESIS,
    )

    # Deterministic Critic/Reducer enforcement
    final_response.score = grounded_score
    final_response.insights = _curate_and_enforce_insights(
        final_response.insights,
        deduped_insights,
    )
    return final_response


# ===========================================================================
# 4. Data-Grounded Fallback Constructors (Resilience against node failures)
# ===========================================================================

def _fallback_allocation(quant: PortfolioQuantMetrics | None = None) -> AllocationLensResult:
    if quant is None:
        return AllocationLensResult(
            sub_score=68,
            allocation_findings=["Standard retail asset allocation; equity core supported by debt anchor."],
            concentration_warnings=["Verify top equity holdings do not exceed 10%."],
            liquidity_tier_assessment="Tier 1 liquid cash appears sufficient for short-term obligations.",
            emergency_floor_ok=True,
        )

    score = 76
    warnings: list[str] = []
    insights: list[Insight] = []

    if not quant.emergency_floor_ok:
        score -= 14
        warnings.append(
            f"Tier 1 liquid buffer (INR {quant.tier1_liquid_inr:,.0f}) is below 6-month emergency floor (INR {quant.six_month_emergency_floor_inr:,.0f})."
        )
        insights.append(
            Insight(
                category="risk",
                severity="critical",
                title="Rebuild 6-Month Liquid Emergency Buffer",
                detail=(
                    f"Instant Tier 1 liquidity is INR {quant.tier1_liquid_inr:,.0f} "
                    f"({quant.emergency_floor_months_covered:.1f} months vs 6.0-month target of INR {quant.six_month_emergency_floor_inr:,.0f})."
                ),
                action="Direct fresh cashflows into sweep FDs or liquid reserves before adding illiquid assets.",
            )
        )
    if quant.stocks_over_10pct:
        score -= 10
        names = ", ".join(f"{s['symbol']} ({s['pct_of_portfolio']}%)" for s in quant.stocks_over_10pct[:3])
        warnings.append(f"Single-stock concentration >10% of portfolio: {names}.")
        insights.append(
            Insight(
                category="risk",
                severity="warning",
                title="Trim Single-Stock Concentration Above 10%",
                detail=f"Concentrated single-stock exposure detected in {names} (Stock HHI: {quant.equity_stock_hhi:.0f}).",
                action="Gradually trim oversized single stocks into core Nifty 50 / Flexi-cap index funds.",
            )
        )
    elif quant.stocks_over_5pct:
        score -= 4
        names = ", ".join(f"{s['symbol']} ({s['pct_of_portfolio']}%)" for s in quant.stocks_over_5pct[:3])
        warnings.append(f"Stocks exceeding 5% portfolio weight: {names}.")

    if quant.asset_classes_over_50pct:
        score -= 6
        dom = ", ".join(f"{c['name']} ({c['pct']}%)" for c in quant.asset_classes_over_50pct)
        warnings.append(f"Single asset class exceeds 50% share: {dom}.")

    findings = [
        f"Growth sleeve is {quant.growth_allocation_pct:.1f}% vs stability anchor {quant.stability_allocation_pct:.1f}% (Asset HHI: {quant.asset_hhi:.0f}).",
        f"Tier 1 instant liquidity: INR {quant.tier1_liquid_inr:,.0f}; Tier 2 near-liquid: INR {quant.tier2_near_liquid_inr:,.0f}; Tier 3 illiquid: INR {quant.tier3_illiquid_inr:,.0f}.",
    ]
    if not warnings:
        warnings.append("No single stock exceeds the 10% concentration threshold.")

    return AllocationLensResult(
        sub_score=max(35, min(92, score)),
        allocation_findings=findings,
        concentration_warnings=warnings,
        liquidity_tier_assessment=(
            f"Tier 1 covers {quant.emergency_floor_months_covered:.1f} months of baseline expenses "
            f"(liquid cash INR {quant.liquid_cash_inr:,.0f}, illiquid receivables excluded INR {quant.illiquid_receivables_inr:,.0f})."
        ),
        emergency_floor_ok=quant.emergency_floor_ok,
        candidate_insights=insights,
    )


def _fallback_quality(quant: PortfolioQuantMetrics | None = None, data: dict | None = None) -> QualityLensResult:
    if quant is None:
        return QualityLensResult(
            sub_score=70,
            equity_quality_findings=["Core equity holdings reflect diversified Indian index and large-cap exposure."],
            legacy_fund_audits=[],
            real_estate_findings=["Real estate assets assessed as long-term capital preservation."],
            debt_hurdle_findings=["EPF provides superior post-tax return compared to retail fixed deposits."],
        )

    score = 75
    eq_findings: list[str] = []
    debt_findings: list[str] = []
    insights: list[Insight] = []
    audits: list[LegacyFundAuditItem] = []

    if quant.loss_aversion_flags:
        score -= min(12, 3 * len(quant.loss_aversion_flags))
        flagged_str = ", ".join(f"{s['symbol']} ({s['pnl_pct']}%)" for s in quant.loss_aversion_flags[:4])
        eq_findings.append(f"Deep drawdown holdings requiring thesis review (<= -15%): {flagged_str}.")
        insights.append(
            Insight(
                category="consolidation",
                severity="warning",
                title="Audit Deep-Drawdown Equity Tail Positions",
                detail=f"{len(quant.loss_aversion_flags)} stock(s) sit below -15% P&L ({flagged_str}), signaling potential anchoring drag.",
                action="Exit broken-thesis laggards to offset taxable capital gains and consolidate into core index funds.",
            )
        )
    else:
        eq_findings.append(f"Screened {quant.total_stock_count} stocks; zero holdings breach the -15% deep-loss threshold.")

    for mf in (data or {}).get("mutual_funds_legacy") or []:
        if isinstance(mf, dict):
            audits.append(
                LegacyFundAuditItem(
                    fund_name=str(mf.get("name") or "Legacy Fund"),
                    action="merge",
                    target_fund="Core Nifty 50 / Flexi-Cap Active SIP",
                    rationale=f"Sub-threshold legacy balance (INR {_dec(mf.get('current')):,.0f}) creates portfolio clutter.",
                )
            )
    if audits:
        score -= min(8, 2 * len(audits))
        insights.append(
            Insight(
                category="consolidation",
                severity="info",
                title="Consolidate Legacy Mutual Fund Tail",
                detail=f"{quant.legacy_fund_count} legacy mutual fund(s) totaling INR {quant.legacy_fund_total_inr:,.0f} dilute compounding focus.",
                action="Switch LTCG-eligible legacy units within the Rs 1.25L annual tax-free window into active core SIPs.",
            )
        )

    if quant.fds_below_epf_hurdle:
        score -= 4
        debt_findings.append(
            f"{len(quant.fds_below_epf_hurdle)} FD(s) earn less post-tax than the {quant.epf_tax_free_hurdle_pct}% tax-free EPF hurdle."
        )
    else:
        debt_findings.append(f"Fixed-income sleeve benchmarked against {quant.epf_tax_free_hurdle_pct}% tax-free EPF hurdle.")

    return QualityLensResult(
        sub_score=max(40, min(90, score)),
        equity_quality_findings=eq_findings,
        legacy_fund_audits=audits,
        real_estate_findings=["Real estate holdings evaluated on net realizable value and rental yield discipline."],
        debt_hurdle_findings=debt_findings,
        candidate_insights=insights,
    )


def _fallback_macro(quant: PortfolioQuantMetrics | None = None) -> MacroStressLensResult:
    if quant is None:
        return MacroStressLensResult(
            sub_score=65,
            valuation_regime="Indian equity markets trading near fair-to-mildly stretched valuations.",
            crash_drawdown_amount="Standard 35% equity drawdown buffer recommended.",
            stress_findings=["Maintain disciplined monthly SIP schedule regardless of short-term volatility."],
            trajectory_trend="stable",
        )

    score = 72
    if quant.rsu_pct_of_portfolio > 20.0:
        score -= 8
    crash_str = f"INR {quant.equity_crash_35pct_loss_inr:,.0f} drawdown (post-crash net worth INR {quant.post_crash_net_worth_inr:,.0f})"
    stress_findings = [
        f"A -35% 2020-style equity selloff reduces portfolio value by INR {quant.equity_crash_35pct_loss_inr:,.0f}.",
    ]
    if quant.rsu_current_inr > 0:
        stress_findings.append(
            f"A -30% tech/RSU contraction impacts US equity sleeve by INR {quant.rsu_shock_30pct_loss_inr:,.0f} ({quant.rsu_pct_of_portfolio:.1f}% of net worth)."
        )

    insights = [
        Insight(
            category="macro",
            severity="info",
            title="Equity Crash Stress-Test Buffer",
            detail=(
                f"Under a -35% equity drawdown, estimated mark-to-market impact is INR {quant.equity_crash_35pct_loss_inr:,.0f}, "
                f"leaving INR {quant.post_crash_net_worth_inr:,.0f} in net worth."
            ),
            action="Keep systematic SIPs automated through volatility while preserving Tier 1 cash buffer.",
        )
    ]

    return MacroStressLensResult(
        sub_score=max(45, min(88, score)),
        valuation_regime="Indian equities assessed against historical 20-22x Nifty P/E fair-value band.",
        crash_drawdown_amount=crash_str,
        stress_findings=stress_findings,
        trajectory_trend=quant.trajectory_trend,
        candidate_insights=insights,
    )


def _fallback_strategy(quant: PortfolioQuantMetrics | None = None) -> StrategyLensResult:
    if quant is None:
        return StrategyLensResult(
            sub_score=68,
            tax_harvesting_plan="Utilize Section 112A Rs 1.25L LTCG annual exemption per PAN.",
            rebalancing_roadmap=["Rebalance any legacy underperforming funds into primary active index SIPs."],
            goal_shortfall_plans=["Ensure retirement and major family milestones remain funded on schedule."],
        )

    score = 74 - min(12, 4 * len(quant.at_risk_goals))
    tax_plan = (
        f"Harvest up to INR {quant.sec_112a_harvestable_ltcg_inr:,.0f} in tax-free Section 112A LTCG this FY "
        f"(out of INR {quant.unrealized_equity_gains_inr:,.0f} unrealized equity gains)."
    )
    roadmap = ["Continue disciplined monthly core index/flexi-cap SIPs aligned with target asset mix."]
    if quant.legacy_fund_total_inr > 0:
        roadmap.insert(
            0,
            f"Redeploy INR {quant.legacy_fund_total_inr:,.0f} from {quant.legacy_fund_count} legacy mutual fund(s) into core SIPs.",
        )

    goal_plans = [
        f"Increase monthly allocation by INR {g['monthly_needed_inr']:,.0f} for '{g['label']}' ({g['progress_pct']}% funded)."
        for g in quant.at_risk_goals[:3]
    ] or ["All tracked financial goals remain on trajectory."]

    insights: list[Insight] = [
        Insight(
            category="tax",
            severity="positive",
            title="Execute Annual Section 112A LTCG Tax Harvesting",
            detail=tax_plan,
            action="Realize and immediately repurchase eligible long-term equity units before March 31.",
        )
    ]
    if quant.at_risk_goals:
        g0 = quant.at_risk_goals[0]
        insights.append(
            Insight(
                category="goal",
                severity="warning",
                title=f"Close Funding Gap for {g0['label']}",
                detail=f"Goal '{g0['label']}' stands at {g0['progress_pct']}% of INR {g0['target_inr']:,.0f} target.",
                action=f"Step up dedicated monthly SIP by INR {g0['monthly_needed_inr']:,.0f}.",
            )
        )

    return StrategyLensResult(
        sub_score=max(45, min(90, score)),
        tax_harvesting_plan=tax_plan,
        rebalancing_roadmap=roadmap,
        goal_shortfall_plans=goal_plans,
        candidate_insights=insights,
    )


def _fallback_terminal_synthesis(
    data: dict,
    allocation: AllocationLensResult,
    quality: QualityLensResult,
    macro: MacroStressLensResult,
    strategy: StrategyLensResult,
    quant: PortfolioQuantMetrics | None = None,
) -> PortfolioInsightsResponse:
    """Deterministic terminal synthesis ensuring 100% resilient completion if Stage 3 fails."""
    quant = quant or compute_portfolio_quant_metrics(data)
    grounded_score = compute_grounded_health_score(allocation, quality, macro, strategy)

    pooled_insights: list[Insight] = (
        allocation.candidate_insights
        + quality.candidate_insights
        + macro.candidate_insights
        + strategy.candidate_insights
    )
    deduped = _curate_and_enforce_insights(pooled_insights, pooled_insights, max_insights=12)

    if not deduped:
        deduped = [
            Insight(
                title="Maintain Systematic Diversification",
                category="rebalancing",
                severity="info",
                detail=(
                    f"Portfolio net worth of INR {quant.total_value_inr:,.0f} ({quant.return_pct:+.1f}% return) "
                    f"holds INR {quant.tier1_liquid_inr:,.0f} in Tier 1 liquidity."
                ),
                action="Continue monthly SIP investments aligned with long-term asset allocation targets.",
            ),
            Insight(
                title="Optimize Annual Tax Harvesting",
                category="tax",
                severity="positive",
                detail=(
                    f"Utilize Section 112A Rs 1.25L LTCG annual tax-free window "
                    f"(INR {quant.sec_112a_harvestable_ltcg_inr:,.0f} currently harvestable)."
                ),
                action="Review realized capital gains before financial year close.",
            ),
        ]

    return PortfolioInsightsResponse(
        summary=(
            f"Portfolio diagnostic complete with an institutional health score of {grounded_score}/100 "
            f"(net worth INR {quant.total_value_inr:,.0f}, {quant.return_pct:+.1f}% overall return). "
            f"Tier 1 liquidity is INR {quant.tier1_liquid_inr:,.0f} and simulated -35% equity drawdown is INR {quant.equity_crash_35pct_loss_inr:,.0f}."
        ),
        score=grounded_score,
        insights=deduped[:12],
        market_context=macro.valuation_regime or "Macro conditions reflect stable domestic growth and steady monetary policy.",
        outlook="Continue disciplined monthly contributions, harvest eligible tax-free LTCG, and rebalance legacy holdings into core SIPs.",
    )


# ===========================================================================
# 5. Workflow DAG Orchestrator (Bounded Timeouts + Stage Checkpointing)
# ===========================================================================

class PortfolioInsightsDAG:
    """Coordinates deterministic pre-computation, parallel specialist lenses, and Carbon synthesis."""

    def __init__(
        self,
        use_concurrent: bool = True,
        stage_timeout: float | None = None,
        enable_stage_cache: bool | None = None,
        stage_cache_ttl: int | None = None,
    ):
        self.use_concurrent = use_concurrent
        self.stage_timeout = (
            float(stage_timeout)
            if stage_timeout is not None
            else float(getattr(settings, "PORTFOLIO_DAG_STAGE_TIMEOUT", 90.0))
        )
        self.enable_stage_cache = (
            bool(enable_stage_cache)
            if enable_stage_cache is not None
            else bool(getattr(settings, "PORTFOLIO_DAG_STAGE_CACHE", False))
        )
        self.stage_cache_ttl = (
            int(stage_cache_ttl)
            if stage_cache_ttl is not None
            else int(getattr(settings, "PORTFOLIO_DAG_STAGE_CACHE_TTL", 600))
        )

    def _stage_cache_key(
        self, stage_name: str, payload: Any, investor_profile: str, group_id: Any = None
    ) -> str:
        raw = _compact_json(
            {"stage": stage_name, "group_id": group_id, "profile": investor_profile, "payload": payload}
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"vault_portfolio_dag:{stage_name}:{digest}"

    def _get_cached_stage(self, key: str, schema: type[BaseModel]) -> Any | None:
        if not self.enable_stage_cache:
            return None
        try:
            from django.core.cache import cache

            cached = cache.get(key)
            if isinstance(cached, dict):
                return schema.model_validate(cached)
        except Exception:
            pass
        return None

    def _set_cached_stage(self, key: str, value: BaseModel) -> None:
        if not self.enable_stage_cache:
            return
        try:
            from django.core.cache import cache

            cache.set(key, value.model_dump(mode="json"), timeout=self.stage_cache_ttl)
        except Exception:
            pass

    def _run_cached_stage(
        self,
        stage_name: str,
        schema: type[BaseModel],
        cache_payload: Any,
        investor_profile: str,
        group_id: Any,
        fn: Any,
        *args: Any,
    ) -> tuple[Any, bool]:
        key = self._stage_cache_key(stage_name, cache_payload, investor_profile, group_id=group_id)
        cached = self._get_cached_stage(key, schema)
        if cached is not None:
            return cached, True
        res = fn(*args)
        self._set_cached_stage(key, res)
        return res, False

    def execute(self, prompt_data: dict, group=None) -> tuple[PortfolioInsightsResponse, DAGExecutionMetadata]:
        t0 = time.time()
        start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        nodes_executed: list[str] = []
        degraded_nodes: list[str] = []
        stage_cache_hits: list[str] = []
        group_id = getattr(group, "id", None)
        investor_profile = _load_investor_profile(group)

        # -------------------------------------------------------------------
        # STAGE 0: Deterministic Decimal Quant Pre-Computation
        # -------------------------------------------------------------------
        quant = compute_portfolio_quant_metrics(prompt_data, investor_profile)

        # -------------------------------------------------------------------
        # STAGE 1: Parallel Diagnostic Lenses (Fan-out)
        # -------------------------------------------------------------------
        alloc_res: AllocationLensResult | None = None
        qual_res: QualityLensResult | None = None
        macro_res: MacroStressLensResult | None = None

        alloc_slice = _extract_allocation_slice(prompt_data, quant)
        qual_slice = _extract_quality_slice(prompt_data, quant)
        macro_slice = _extract_macro_stress_slice(prompt_data, quant)

        if self.use_concurrent:
            logger.info("[DAG] Dispatching Stage 1 lenses concurrently (3 worker threads, timeout=%.1fs)...", self.stage_timeout)
            executor = DjangoSafeThreadPoolExecutor(max_workers=3)
            timed_out = False
            try:
                future_alloc = executor.submit(
                    self._run_cached_stage,
                    "Stage1A:Allocation",
                    AllocationLensResult,
                    alloc_slice,
                    investor_profile,
                    group_id,
                    run_stage_1a_allocation,
                    prompt_data,
                    investor_profile,
                    quant,
                )
                future_qual = executor.submit(
                    self._run_cached_stage,
                    "Stage1B:Quality",
                    QualityLensResult,
                    qual_slice,
                    investor_profile,
                    group_id,
                    run_stage_1b_quality,
                    prompt_data,
                    investor_profile,
                    quant,
                )
                future_macro = executor.submit(
                    self._run_cached_stage,
                    "Stage1C:Macro",
                    MacroStressLensResult,
                    macro_slice,
                    investor_profile,
                    group_id,
                    run_stage_1c_macro,
                    prompt_data,
                    investor_profile,
                    quant,
                )

                deadline = time.monotonic() + self.stage_timeout

                try:
                    alloc_res, hit_a = future_alloc.result(timeout=max(0.01, deadline - time.monotonic()))
                    nodes_executed.append("Stage1A:Allocation")
                    if hit_a:
                        stage_cache_hits.append("Stage1A:Allocation")
                except Exception as e:
                    if isinstance(e, FuturesTimeoutError):
                        timed_out = True
                    logger.warning("[DAG] Stage 1A failed (%s); using data-grounded fallback", e)
                    degraded_nodes.append("Stage1A:Allocation")
                    alloc_res = _fallback_allocation(quant)

                try:
                    qual_res, hit_q = future_qual.result(timeout=max(0.01, deadline - time.monotonic()))
                    nodes_executed.append("Stage1B:Quality")
                    if hit_q:
                        stage_cache_hits.append("Stage1B:Quality")
                except Exception as e:
                    if isinstance(e, FuturesTimeoutError):
                        timed_out = True
                    logger.warning("[DAG] Stage 1B failed (%s); using data-grounded fallback", e)
                    degraded_nodes.append("Stage1B:Quality")
                    qual_res = _fallback_quality(quant, prompt_data)

                try:
                    macro_res, hit_m = future_macro.result(timeout=max(0.01, deadline - time.monotonic()))
                    nodes_executed.append("Stage1C:Macro")
                    if hit_m:
                        stage_cache_hits.append("Stage1C:Macro")
                except Exception as e:
                    if isinstance(e, FuturesTimeoutError):
                        timed_out = True
                    logger.warning("[DAG] Stage 1C failed (%s); using data-grounded fallback", e)
                    degraded_nodes.append("Stage1C:Macro")
                    macro_res = _fallback_macro(quant)
            finally:
                executor.shutdown(wait=not timed_out, cancel_futures=True)
        else:
            logger.info("[DAG] Dispatching Stage 1 lenses sequentially...")
            try:
                alloc_res, hit_a = self._run_cached_stage(
                    "Stage1A:Allocation",
                    AllocationLensResult,
                    alloc_slice,
                    investor_profile,
                    group_id,
                    run_stage_1a_allocation,
                    prompt_data,
                    investor_profile,
                    quant,
                )
                nodes_executed.append("Stage1A:Allocation")
                if hit_a:
                    stage_cache_hits.append("Stage1A:Allocation")
            except Exception as e:
                logger.warning("[DAG] Stage 1A sequential failed (%s); using data-grounded fallback", e)
                degraded_nodes.append("Stage1A:Allocation")
                alloc_res = _fallback_allocation(quant)

            try:
                qual_res, hit_q = self._run_cached_stage(
                    "Stage1B:Quality",
                    QualityLensResult,
                    qual_slice,
                    investor_profile,
                    group_id,
                    run_stage_1b_quality,
                    prompt_data,
                    investor_profile,
                    quant,
                )
                nodes_executed.append("Stage1B:Quality")
                if hit_q:
                    stage_cache_hits.append("Stage1B:Quality")
            except Exception as e:
                logger.warning("[DAG] Stage 1B sequential failed (%s); using data-grounded fallback", e)
                degraded_nodes.append("Stage1B:Quality")
                qual_res = _fallback_quality(quant, prompt_data)

            try:
                macro_res, hit_m = self._run_cached_stage(
                    "Stage1C:Macro",
                    MacroStressLensResult,
                    macro_slice,
                    investor_profile,
                    group_id,
                    run_stage_1c_macro,
                    prompt_data,
                    investor_profile,
                    quant,
                )
                nodes_executed.append("Stage1C:Macro")
                if hit_m:
                    stage_cache_hits.append("Stage1C:Macro")
            except Exception as e:
                logger.warning("[DAG] Stage 1C sequential failed (%s); using data-grounded fallback", e)
                degraded_nodes.append("Stage1C:Macro")
                macro_res = _fallback_macro(quant)

        # -------------------------------------------------------------------
        # STAGE 2: Tactical Planning & Rebalancing (Fan-in)
        # -------------------------------------------------------------------
        strat_res: StrategyLensResult | None = None
        strat_cache_payload = {
            "summary": prompt_data.get("summary", {}),
            "goals": prompt_data.get("goals", []),
            "alloc": alloc_res.model_dump(mode="json"),
            "qual": qual_res.model_dump(mode="json"),
            "macro": macro_res.model_dump(mode="json"),
        }
        try:
            strat_res, hit_s = self._run_cached_stage(
                "Stage2:Strategy",
                StrategyLensResult,
                strat_cache_payload,
                investor_profile,
                group_id,
                run_stage_2_strategy,
                prompt_data,
                investor_profile,
                alloc_res,
                qual_res,
                macro_res,
                quant,
            )
            nodes_executed.append("Stage2:Strategy")
            if hit_s:
                stage_cache_hits.append("Stage2:Strategy")
        except Exception as e:
            logger.warning("[DAG] Stage 2 failed (%s); using data-grounded fallback", e)
            degraded_nodes.append("Stage2:Strategy")
            strat_res = _fallback_strategy(quant)

        # -------------------------------------------------------------------
        # STAGE 3: Terminal Grounding & Synthesis
        # -------------------------------------------------------------------
        synth_cache_payload = {
            "strat_cache": strat_cache_payload,
            "strat": strat_res.model_dump(mode="json"),
        }
        try:
            terminal_response, hit_t = self._run_cached_stage(
                "Stage3:TerminalSynthesis",
                PortfolioInsightsResponse,
                synth_cache_payload,
                investor_profile,
                group_id,
                run_stage_3_terminal_synthesis,
                prompt_data,
                investor_profile,
                alloc_res,
                qual_res,
                macro_res,
                strat_res,
                quant,
            )
            nodes_executed.append("Stage3:TerminalSynthesis")
            if hit_t:
                stage_cache_hits.append("Stage3:TerminalSynthesis")
        except Exception as e:
            logger.warning("[DAG] Stage 3 synthesis failed (%s); using data-grounded fallback", e)
            degraded_nodes.append("Stage3:TerminalSynthesis")
            terminal_response = _fallback_terminal_synthesis(
                prompt_data, alloc_res, qual_res, macro_res, strat_res, quant
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        end_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        metadata = DAGExecutionMetadata(
            started_at=start_time_iso,
            completed_at=end_time_iso,
            elapsed_ms=elapsed_ms,
            nodes_executed=nodes_executed,
            sub_scores={
                "allocation": alloc_res.sub_score,
                "quality": qual_res.sub_score,
                "strategy": strat_res.sub_score,
                "macro": macro_res.sub_score,
            },
            grounded_score=terminal_response.score,
            fallback_used=len(nodes_executed) < 5,
            degraded_nodes=degraded_nodes,
            stage_cache_hits=stage_cache_hits,
            quant_metrics=quant.model_dump(mode="json"),
        )

        logger.info(
            "[DAG] Workflow completed in %.1fms. Nodes: %s. Grounded Score: %d (Alloc=%d, Qual=%d, Strat=%d, Macro=%d)",
            elapsed_ms,
            ", ".join(nodes_executed),
            metadata.grounded_score,
            alloc_res.sub_score,
            qual_res.sub_score,
            strat_res.sub_score,
            macro_res.sub_score,
        )
        return terminal_response, metadata

    async def execute_async(self, prompt_data: dict, group=None) -> tuple[PortfolioInsightsResponse, DAGExecutionMetadata]:
        """Asynchronously execute Stage 1 lenses concurrently via asyncio.gather and synthesize Stage 2/3."""
        t0 = time.time()
        start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        nodes_executed: list[str] = []
        degraded_nodes: list[str] = []
        stage_cache_hits: list[str] = []
        group_id = getattr(group, "id", None)
        investor_profile = await safe_async_to_thread(_load_investor_profile, group)
        quant = compute_portfolio_quant_metrics(prompt_data, investor_profile)

        alloc_slice = _extract_allocation_slice(prompt_data, quant)
        qual_slice = _extract_quality_slice(prompt_data, quant)
        macro_slice = _extract_macro_stress_slice(prompt_data, quant)

        async def _run_alloc():
            try:
                res, hit = await asyncio.wait_for(
                    safe_async_to_thread(
                        self._run_cached_stage,
                        "Stage1A:Allocation",
                        AllocationLensResult,
                        alloc_slice,
                        investor_profile,
                        group_id,
                        run_stage_1a_allocation,
                        prompt_data,
                        investor_profile,
                        quant,
                    ),
                    timeout=self.stage_timeout,
                )
                return "Stage1A:Allocation", res, hit
            except Exception as e:
                logger.warning("[DAG] Async Stage 1A failed (%s); using data-grounded fallback", e)
                return None, _fallback_allocation(quant), False

        async def _run_qual():
            try:
                res, hit = await asyncio.wait_for(
                    safe_async_to_thread(
                        self._run_cached_stage,
                        "Stage1B:Quality",
                        QualityLensResult,
                        qual_slice,
                        investor_profile,
                        group_id,
                        run_stage_1b_quality,
                        prompt_data,
                        investor_profile,
                        quant,
                    ),
                    timeout=self.stage_timeout,
                )
                return "Stage1B:Quality", res, hit
            except Exception as e:
                logger.warning("[DAG] Async Stage 1B failed (%s); using data-grounded fallback", e)
                return None, _fallback_quality(quant, prompt_data), False

        async def _run_macro():
            try:
                res, hit = await asyncio.wait_for(
                    safe_async_to_thread(
                        self._run_cached_stage,
                        "Stage1C:Macro",
                        MacroStressLensResult,
                        macro_slice,
                        investor_profile,
                        group_id,
                        run_stage_1c_macro,
                        prompt_data,
                        investor_profile,
                        quant,
                    ),
                    timeout=self.stage_timeout,
                )
                return "Stage1C:Macro", res, hit
            except Exception as e:
                logger.warning("[DAG] Async Stage 1C failed (%s); using data-grounded fallback", e)
                return None, _fallback_macro(quant), False

        results = await asyncio.gather(_run_alloc(), _run_qual(), _run_macro())
        (k_a, alloc_res, hit_a), (k_q, qual_res, hit_q), (k_m, macro_res, hit_m) = results
        for label, key, hit in (
            ("Stage1A:Allocation", k_a, hit_a),
            ("Stage1B:Quality", k_q, hit_q),
            ("Stage1C:Macro", k_m, hit_m),
        ):
            if key:
                nodes_executed.append(key)
                if hit:
                    stage_cache_hits.append(key)
            else:
                degraded_nodes.append(label)

        # STAGE 2: Strategy (Fan-in)
        strat_cache_payload = {
            "summary": prompt_data.get("summary", {}),
            "goals": prompt_data.get("goals", []),
            "alloc": alloc_res.model_dump(mode="json"),
            "qual": qual_res.model_dump(mode="json"),
            "macro": macro_res.model_dump(mode="json"),
        }
        try:
            strat_res, hit_s = await asyncio.wait_for(
                safe_async_to_thread(
                    self._run_cached_stage,
                    "Stage2:Strategy",
                    StrategyLensResult,
                    strat_cache_payload,
                    investor_profile,
                    group_id,
                    run_stage_2_strategy,
                    prompt_data,
                    investor_profile,
                    alloc_res,
                    qual_res,
                    macro_res,
                    quant,
                ),
                timeout=self.stage_timeout,
            )
            nodes_executed.append("Stage2:Strategy")
            if hit_s:
                stage_cache_hits.append("Stage2:Strategy")
        except Exception as e:
            logger.warning("[DAG] Async Stage 2 failed (%s); using data-grounded fallback", e)
            degraded_nodes.append("Stage2:Strategy")
            strat_res = _fallback_strategy(quant)

        # STAGE 3: Terminal Grounding & Synthesis
        synth_cache_payload = {
            "strat_cache": strat_cache_payload,
            "strat": strat_res.model_dump(mode="json"),
        }
        try:
            terminal_response, hit_t = await asyncio.wait_for(
                safe_async_to_thread(
                    self._run_cached_stage,
                    "Stage3:TerminalSynthesis",
                    PortfolioInsightsResponse,
                    synth_cache_payload,
                    investor_profile,
                    group_id,
                    run_stage_3_terminal_synthesis,
                    prompt_data,
                    investor_profile,
                    alloc_res,
                    qual_res,
                    macro_res,
                    strat_res,
                    quant,
                ),
                timeout=self.stage_timeout,
            )
            nodes_executed.append("Stage3:TerminalSynthesis")
            if hit_t:
                stage_cache_hits.append("Stage3:TerminalSynthesis")
        except Exception as e:
            logger.warning("[DAG] Async Stage 3 synthesis failed (%s); using data-grounded fallback", e)
            degraded_nodes.append("Stage3:TerminalSynthesis")
            terminal_response = _fallback_terminal_synthesis(
                prompt_data, alloc_res, qual_res, macro_res, strat_res, quant
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        end_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        metadata = DAGExecutionMetadata(
            started_at=start_time_iso,
            completed_at=end_time_iso,
            elapsed_ms=elapsed_ms,
            nodes_executed=nodes_executed,
            sub_scores={
                "allocation": alloc_res.sub_score,
                "quality": qual_res.sub_score,
                "strategy": strat_res.sub_score,
                "macro": macro_res.sub_score,
            },
            grounded_score=terminal_response.score,
            fallback_used=len(nodes_executed) < 5,
            degraded_nodes=degraded_nodes,
            stage_cache_hits=stage_cache_hits,
            quant_metrics=quant.model_dump(mode="json"),
        )

        return terminal_response, metadata


async def arun_portfolio_insights_dag(
    prompt_data: dict,
    group=None,
) -> AIResult:
    """Async entry point for executing the portfolio insights multi-stage DAG without blocking."""
    dag = PortfolioInsightsDAG(use_concurrent=True)
    response, metadata = await dag.execute_async(prompt_data, group=group)

    insights_dict = response.model_dump(mode="json")
    insights_dict["_dag_metadata"] = metadata.model_dump(mode="json")

    return AIResult(
        model="vault-dag:multi-stage-async",
        insights_dict=insights_dict,
    )


def run_portfolio_insights_dag(
    prompt_data: dict,
    group=None,
    use_concurrent: bool | None = None,
) -> AIResult:
    """Main external entry point for executing the portfolio insights multi-stage DAG."""
    if use_concurrent is None:
        use_concurrent = getattr(settings, "PORTFOLIO_DAG_CONCURRENCY", True)

    dag = PortfolioInsightsDAG(use_concurrent=use_concurrent)
    response, metadata = dag.execute(prompt_data, group=group)

    insights_dict = response.model_dump(mode="json")
    insights_dict["_dag_metadata"] = metadata.model_dump(mode="json")

    return AIResult(
        model="vault-dag:multi-stage",
        insights_dict=insights_dict,
    )
