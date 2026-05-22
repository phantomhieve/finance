#!/usr/bin/env python
"""
seed_data.py — Idempotent seed script for local Vault development.

Usage:
    python seed_data.py

Creates:
  - AccountGroup: "Household"
  - Users: atul (PRIMARY), spouse (ACCOUNT_HOLDER), landlord (LANDLORD)
  - Categories, Transactions (12 months FY 2024-25), HRA Expenses
  - Financial Goals + GoalIncrements + MonthlyGoalAdjustments
  - Portfolio: ZerodhaAccount, StockHoldings, MutualFundHoldings
  - EPF entries, NPS entries, Fixed Deposits, Cash, Bonds, Crypto
  - CommodityHolding (gold, silver) + CommodityPrice
  - US Stock RSU holding
  - Portfolio FinancialGoal milestones (50L, 1Cr)

All operations use get_or_create — safe to re-run.
"""

import os
import sys
import django
from decimal import Decimal
from datetime import date, datetime

# ── Bootstrap Django ──────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pftracker.settings")

# Load .env before Django initialises so DATABASE_URL is available
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

django.setup()

# ── Imports after setup ───────────────────────────────────────────────────────
from tracker.models import (
    AccountGroup, User, Category, Transaction,
    HRAExpense, FinancialGoal as TrackerFinancialGoal,
    GoalIncrement, MonthlyGoalAdjustment,
)
from portfolio.models import (
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit, CashPosition, BondHolding,
    CryptoHolding, CommodityHolding, CommodityPrice,
    USStockHolding, FinancialGoal as PortfolioFinancialGoal,
    MonthlySnapshot,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def d(y, m, day=1):
    return date(y, m, day)


def say(msg):
    print(f"  ✓  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. AccountGroup
# ─────────────────────────────────────────────────────────────────────────────
print("\n── AccountGroup ──────────────────────────────────────────────")
group, _ = AccountGroup.objects.get_or_create(name="Household")
group.set_portfolio_password("portfolio123")
group.save()
say(f"AccountGroup '{group.name}' (portfolio_password: portfolio123)")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Users
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Users ─────────────────────────────────────────────────────")
USERS = [
    dict(username="atul",     email="atul@vault.local",     user_type="PRIMARY",        first_name="Atul",    last_name="Sharma",  is_staff=True, is_superuser=True),
    dict(username="spouse",   email="spouse@vault.local",   user_type="ACCOUNT_HOLDER", first_name="Kanika",  last_name="Sharma",  is_staff=False, is_superuser=False),
    dict(username="landlord", email="landlord@vault.local", user_type="LANDLORD",       first_name="Ramesh",  last_name="Gupta",   is_staff=False, is_superuser=False),
]

user_objs = {}
for u in USERS:
    uname = u.pop("username")
    obj, created = User.objects.get_or_create(username=uname, defaults={**u, "group": group})
    if created:
        obj.set_password("password123")
        obj.group = group
        obj.save()
    else:
        # Ensure group is linked even on re-run
        obj.group = group
        obj.save(update_fields=["group"])
    user_objs[uname] = obj
    say(f"User '{uname}' ({obj.get_user_type_display()})")

atul = user_objs["atul"]
spouse = user_objs["spouse"]

# ─────────────────────────────────────────────────────────────────────────────
# 3. Categories
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Categories ────────────────────────────────────────────────")
CATS = [
    ("Salary",          "INCOME",   atul),
    ("Freelance",       "INCOME",   atul),
    ("Spouse Salary",   "INCOME",   spouse),
    ("PPF",             "SAVINGS",  atul),
    ("Mutual Fund SIP", "SAVINGS",  atul),
    ("Emergency Fund",  "SAVINGS",  atul),
    ("Bank Transfer",   "TRANSFER", atul),
    ("Rent",            "EXPENSE",  atul),
    ("Utilities",       "EXPENSE",  atul),
]

cat_objs = {}
for name, typ, user in CATS:
    obj, _ = Category.objects.get_or_create(name=name, type=typ, user=user)
    cat_objs[name] = obj
    say(f"Category '{name}' ({typ}) for {user.username}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Transactions — FY 2024-25 (Apr 2024 – Mar 2025)
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Transactions (FY 2024-25) ─────────────────────────────────")

MONTHLY_SAVINGS = [
    # (month_date, savings_amt, transfer_amt, extra_income)
    (d(2024,  4, 5), 55_000, 20_000, 0),
    (d(2024,  5, 5), 55_000, 20_000, 0),
    (d(2024,  6, 5), 55_000, 20_000, 8_000),   # freelance
    (d(2024,  7, 5), 60_000, 20_000, 0),
    (d(2024,  8, 5), 60_000, 25_000, 0),
    (d(2024,  9, 5), 60_000, 25_000, 0),
    (d(2024, 10, 5), 65_000, 25_000, 12_000),  # bonus
    (d(2024, 11, 5), 65_000, 25_000, 0),
    (d(2024, 12, 5), 65_000, 30_000, 0),
    (d(2025,  1, 5), 70_000, 30_000, 0),
    (d(2025,  2, 5), 70_000, 30_000, 0),
    (d(2025,  3, 5), 70_000, 30_000, 15_000),  # tax refund
]

savings_cat = cat_objs["Mutual Fund SIP"]
transfer_cat = cat_objs["Bank Transfer"]
income_cat = cat_objs["Freelance"]

for dt, sav, tra, extra in MONTHLY_SAVINGS:
    Transaction.objects.get_or_create(
        user=atul, date=dt, type="SAVINGS",
        defaults=dict(amount=sav, category=savings_cat, remarks="Monthly SIP")
    )
    Transaction.objects.get_or_create(
        user=atul, date=dt, type="TRANSFER",
        defaults=dict(amount=tra, category=transfer_cat, remarks="Spouse account transfer")
    )
    if extra:
        Transaction.objects.get_or_create(
            user=atul, date=dt, type="EXTRA_INCOME",
            defaults=dict(amount=extra, category=income_cat, remarks="Freelance/bonus")
        )

say("Created 12 months of savings + transfer + extra-income transactions")

# ─────────────────────────────────────────────────────────────────────────────
# 5. HRA Expenses — FY 2024-25
# ─────────────────────────────────────────────────────────────────────────────
print("\n── HRA Expenses ──────────────────────────────────────────────")

RENT = 28_000
for m in range(4, 13):
    HRAExpense.objects.get_or_create(
        user=atul, date=d(2024, m, 1), hra_type="RENT_PAID",
        defaults=dict(amount=RENT, expense_type="Rent", remarks="Monthly rent", mode_of_payment="Bank Transfer")
    )
for m in range(1, 4):
    HRAExpense.objects.get_or_create(
        user=atul, date=d(2025, m, 1), hra_type="RENT_PAID",
        defaults=dict(amount=RENT, expense_type="Rent", remarks="Monthly rent", mode_of_payment="Bank Transfer")
    )

# A couple of expenses
HRAExpense.objects.get_or_create(
    user=atul, date=d(2024, 6, 15), hra_type="EXPENSE",
    defaults=dict(amount=5_500, expense_type="Maintenance", remarks="Society maintenance Q1", mode_of_payment="UPI")
)
HRAExpense.objects.get_or_create(
    user=atul, date=d(2024, 9, 15), hra_type="EXPENSE",
    defaults=dict(amount=5_500, expense_type="Maintenance", remarks="Society maintenance Q2", mode_of_payment="UPI")
)
# A revert
HRAExpense.objects.get_or_create(
    user=atul, date=d(2024, 8, 20), hra_type="REVERT",
    defaults=dict(amount=2_000, expense_type="Revert", remarks="Landlord returned excess", mode_of_payment="Bank Transfer", is_revert=True)
)

say("HRA expenses: 12 months rent + 2 maintenance + 1 revert")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Financial Goals (tracker) + GoalIncrements + MonthlyGoalAdjustments
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Tracker Financial Goals ───────────────────────────────────")

# Base monthly goal of ₹55k, step up to ₹60k from Jul 2024, ₹65k from Oct 2024
GoalIncrement.objects.get_or_create(
    user=atul, effective_month=d(2024, 4, 1),
    defaults=dict(increment_amount=0, reason="Base monthly goal ₹55,000")
)
GoalIncrement.objects.get_or_create(
    user=atul, effective_month=d(2024, 7, 1),
    defaults=dict(increment_amount=5_000, reason="Salary hike — Jul 2024")
)
GoalIncrement.objects.get_or_create(
    user=atul, effective_month=d(2024, 10, 1),
    defaults=dict(increment_amount=5_000, reason="Promotion — Oct 2024")
)
say("3 GoalIncrements created (base + 2 step-ups)")

# One-off adjustment for a vacation month
MonthlyGoalAdjustment.objects.get_or_create(
    user=atul, month=d(2024, 12, 1),
    defaults=dict(adjustment_amount=-10_000, reason="Vacation month — reduced target")
)
say("1 MonthlyGoalAdjustment (Dec 2024 vacation)")

# ─────────────────────────────────────────────────────────────────────────────
# 7. ZerodhaAccount + Stock + MF Holdings
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Zerodha ────────────────────────────────────────")

zerodha, _ = ZerodhaAccount.objects.get_or_create(
    slug="atul-zerodha",
    defaults=dict(
        group=group,
        name="Atul — Zerodha",
        sheet_id="",  # fill in real Sheet ID if needed
        sheet_range_stocks="Holdings!A2:G",
        sheet_range_index_mf="Index MF!A2:F",
        sheet_range_other_mf="Other MF!A2:F",
    )
)
say(f"ZerodhaAccount '{zerodha.name}'")

STOCKS = [
    ("RELIANCE",  12,  28_540, 31_200),
    ("HDFCBANK",  25,  38_750, 42_500),
    ("INFY",      40,  58_000, 63_200),
    ("TCS",       10,  37_200, 41_000),
    ("BAJFINANCE", 8,  30_400, 35_800),
    ("ICICIBANK", 50,  42_500, 52_000),
    ("SBIN",      80,  38_400, 48_000),
    ("WIPRO",    100,  48_000, 52_500),
    ("LTIM",      15,  67_500, 75_000),
    ("AXISBANK",  60,  42_000, 49_800),
]
for sym, qty, pv, cv in STOCKS:
    StockHolding.objects.get_or_create(
        account=zerodha, symbol=sym,
        defaults=dict(quantity=qty, purchase_value=pv, current_value=cv)
    )
say(f"{len(STOCKS)} stock holdings")

MFS = [
    ("Nifty 50 Index Fund — Direct Growth",                          "INDEX", Decimal("1234.567"), 85_000, 98_500),
    ("Nifty Next 50 Index Fund — Direct Growth",                     "INDEX", Decimal("876.432"),  60_000, 70_200),
    ("Nifty Midcap 150 Index Fund — Direct Growth",                  "INDEX", Decimal("543.210"),  45_000, 55_100),
    ("Parag Parikh Flexi Cap Fund — Direct Growth",                  "OTHER", Decimal("321.100"),  50_000, 62_300),
    ("SBI Small Cap Fund — Direct Growth",                           "OTHER", Decimal("210.500"),  30_000, 41_000),
    ("HDFC Balanced Advantage Fund — Direct Growth",                 "OTHER", Decimal("150.000"),  20_000, 24_500),
]
for fname, ftype, units, pv, cv in MFS:
    MutualFundHolding.objects.get_or_create(
        account=zerodha, fund_name=fname,
        defaults=dict(fund_type=ftype, units=units, purchase_value=pv, current_value=cv)
    )
say(f"{len(MFS)} mutual fund holdings")

# ─────────────────────────────────────────────────────────────────────────────
# 8. EPF Entries
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: EPF ────────────────────────────────────────────")

EPF_DATA = [
    (d(2024,  4, 30), "CONTRIBUTION", 12_000, "Apr 2024 EPF contribution"),
    (d(2024,  5, 31), "CONTRIBUTION", 12_000, "May 2024"),
    (d(2024,  6, 30), "CONTRIBUTION", 12_000, "Jun 2024"),
    (d(2024,  7, 31), "CONTRIBUTION", 13_000, "Jul 2024 (post hike)"),
    (d(2024,  8, 31), "CONTRIBUTION", 13_000, "Aug 2024"),
    (d(2024,  9, 30), "CONTRIBUTION", 13_000, "Sep 2024"),
    (d(2024, 10, 31), "CONTRIBUTION", 14_000, "Oct 2024 (post promotion)"),
    (d(2024, 11, 30), "CONTRIBUTION", 14_000, "Nov 2024"),
    (d(2024, 12, 31), "CONTRIBUTION", 14_000, "Dec 2024"),
    (d(2025,  1, 31), "CONTRIBUTION", 14_500, "Jan 2025"),
    (d(2025,  2, 28), "CONTRIBUTION", 14_500, "Feb 2025"),
    (d(2025,  3, 31), "CONTRIBUTION", 14_500, "Mar 2025"),
    (d(2025,  3, 31), "INTEREST",     35_200, "FY 2024-25 interest @ 8.25%"),
]
for dt, etype, amt, rem in EPF_DATA:
    EPFEntry.objects.get_or_create(
        group=group, date=dt, entry_type=etype, amount=amt,
        defaults=dict(remarks=rem)
    )
say(f"{len(EPF_DATA)} EPF entries")

# ─────────────────────────────────────────────────────────────────────────────
# 9. NPS Entries
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: NPS ────────────────────────────────────────────")

NPS_DATA = [
    (d(2024,  6, 30),  6_000,  1_200, 1_82_500, "Q1 FY25"),
    (d(2024,  9, 30),  6_000,  1_800, 1_91_300, "Q2 FY25"),
    (d(2024, 12, 31),  6_000,  2_400, 2_00_700, "Q3 FY25"),
    (d(2025,  3, 31),  6_000,  3_200, 2_09_900, "Q4 FY25"),
]
for dt, cont, interest, bal, rem in NPS_DATA:
    NPSEntry.objects.get_or_create(
        group=group, date=dt,
        defaults=dict(contribution=cont, interest_earned=interest, total_balance=bal, remarks=rem)
    )
say(f"{len(NPS_DATA)} NPS entries")

# ─────────────────────────────────────────────────────────────────────────────
# 10. Fixed Deposits
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Fixed Deposits ─────────────────────────────────")

FDS = [
    ("SBI FD — Emergency Fund",   "Atul Acc",     3_00_000, Decimal("7.10"), "QUARTERLY", d(2024, 2, 15), d(2026, 2, 15), True,  "Emergency corpus FD"),
    ("HDFC FD — Short Term",      "Atul Acc",     1_50_000, Decimal("7.25"), "QUARTERLY", d(2024, 8,  1), d(2025, 8,  1), True,  "Short-term parking"),
    ("Post Office TD",            "HUF Acc",      5_00_000, Decimal("7.50"), "ANNUAL",    d(2023, 4,  1), d(2028, 4,  1), True,  "5-year TD"),
    ("ICICI FD — Matured",        "Atul Acc",     2_00_000, Decimal("6.80"), "QUARTERLY", d(2022, 1,  1), d(2024, 1,  1), False, "Matured Jan 2024"),
]
for name, acct, principal, rate, comp, start, mat, active, rem in FDS:
    FixedDeposit.objects.get_or_create(
        group=group, name=name,
        defaults=dict(
            account_name=acct, principal=principal, interest_rate=rate,
            compounding=comp, start_date=start, maturity_date=mat,
            is_active=active, remarks=rem
        )
    )
say(f"{len(FDS)} fixed deposits (3 active, 1 matured)")

# ─────────────────────────────────────────────────────────────────────────────
# 11. Cash Positions
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Cash ───────────────────────────────────────────")

CASH = [
    ("SBI Savings — Atul",    1_85_000, "Primary savings account"),
    ("HDFC Savings — Kanika", 45_000,   "Spouse savings account"),
    ("Cash in hand",          15_000,   "Physical cash"),
    ("Cash lent — Rahul",     50_000,   "Lent to friend, to be returned"),
]
for name, amt, rem in CASH:
    CashPosition.objects.get_or_create(
        group=group, name=name,
        defaults=dict(amount=amt, remarks=rem)
    )
say(f"{len(CASH)} cash positions")

# ─────────────────────────────────────────────────────────────────────────────
# 12. Bonds
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Bonds ──────────────────────────────────────────")

BONDS = [
    ("RBI Floating Rate Bond — Atul Acc", 2_00_000, "7yr RBI FRB"),
    ("Sovereign Gold Bond 2026",           85_000,  "SGB Series"),
]
for acct, amt, rem in BONDS:
    BondHolding.objects.get_or_create(
        group=group, account_name=acct,
        defaults=dict(amount=amt, remarks=rem)
    )
say(f"{len(BONDS)} bond holdings")

# ─────────────────────────────────────────────────────────────────────────────
# 13. Crypto
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Crypto ─────────────────────────────────────────")

CRYPTO = [
    ("Bitcoin (BTC)",  45_000, 72_000, "Small allocation via CoinDCX"),
    ("Ethereum (ETH)", 20_000, 28_500, "ETH via CoinDCX"),
]
for name, invested, current, rem in CRYPTO:
    CryptoHolding.objects.get_or_create(
        group=group, name=name,
        defaults=dict(amount_invested=invested, current_value=current, remarks=rem)
    )
say(f"{len(CRYPTO)} crypto holdings")

# ─────────────────────────────────────────────────────────────────────────────
# 14. Commodity Holdings (Gold & Silver)
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Commodities ────────────────────────────────────")

COMMODITIES = [
    ("GOLD",   "20gm Coin — 1 (24k)",        "24k", Decimal("20.00"),  Decimal("6100.00")),
    ("GOLD",   "10gm Bar — 1 (22k)",          "22k", Decimal("10.00"),  Decimal("5800.00")),
    ("GOLD",   "Jewellery — Necklace (22k)",  "22k", Decimal("35.00"),  Decimal("5750.00")),
    ("SILVER", "Silver Coins 100gm",          "999", Decimal("100.00"), Decimal("78.50")),
    ("SILVER", "Silver Bar 500gm",            "999", Decimal("500.00"), Decimal("78.00")),
]
for ctype, desc, purity, weight, ppg in COMMODITIES:
    CommodityHolding.objects.get_or_create(
        group=group, commodity_type=ctype, description=desc,
        defaults=dict(purity=purity, weight_grams=weight, purchase_price_per_gram=ppg)
    )
say(f"{len(COMMODITIES)} commodity holdings (gold + silver)")

# Current commodity prices
CommodityPrice.objects.update_or_create(
    commodity_type="GOLD",
    defaults=dict(rate_per_gram=Decimal("9480.00"))
)
CommodityPrice.objects.update_or_create(
    commodity_type="SILVER",
    defaults=dict(rate_per_gram=Decimal("97.50"))
)
say("CommodityPrice: GOLD ₹9,480/g, SILVER ₹97.50/g")

# ─────────────────────────────────────────────────────────────────────────────
# 15. US Stock RSU Holdings
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: US Stocks (RSU) ────────────────────────────────")

RSU_DATA = [
    ("UBER", "Uber Technologies", 50, d(2023, 3, 1),  Decimal("36.25"), Decimal("72.50"),  Decimal("82.50"),  Decimal("83.20")),
    ("UBER", "Uber Technologies", 50, d(2024, 3, 1),  Decimal("78.10"), Decimal("72.50"),  Decimal("83.50"),  Decimal("83.20")),
]
for sym, company, qty, vest, pp_usd, cp_usd, pp_inr_rate, cp_inr_rate in RSU_DATA:
    USStockHolding.objects.get_or_create(
        group=group, symbol=sym, vest_date=vest,
        defaults=dict(
            company_name=company,
            quantity=qty,
            purchase_price_usd=pp_usd,
            current_price_usd=cp_usd,
            purchase_usd_inr=pp_inr_rate,
            current_usd_inr=cp_inr_rate,
            remarks=f"RSU vest {vest}",
        )
    )
say(f"{len(RSU_DATA)} US stock RSU batches")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Portfolio Financial Goal Milestones
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Financial Goal Milestones ──────────────────────")

MILESTONES = [
    ("25L",  25_00_000, 1),
    ("50L",  50_00_000, 2),
    ("1Cr", 1_00_00_000, 3),
]
for label, target, order in MILESTONES:
    PortfolioFinancialGoal.objects.get_or_create(
        group=group, label=label,
        defaults=dict(target_amount=target, sort_order=order)
    )
say(f"{len(MILESTONES)} portfolio milestones (25L → 50L → 1Cr)")

# ─────────────────────────────────────────────────────────────────────────────
# 17. Monthly Portfolio Snapshot (latest month)
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Portfolio: Monthly Snapshot ───────────────────────────────")

MonthlySnapshot.objects.get_or_create(
    group=group, month=d(2025, 3, 1),
    defaults=dict(
        data={
            "zerodha":    {"invested": 7_00_000,  "current": 8_52_000,  "returns": 1_52_000},
            "epf":        {"invested": 4_00_000,  "current": 4_00_000,  "returns": 0},
            "nps":        {"invested": 2_00_000,  "current": 2_09_900,  "returns": 9_900},
            "fd":         {"invested": 11_50_000, "current": 12_20_000, "returns": 70_000},
            "cash":       {"invested": 2_95_000,  "current": 2_95_000,  "returns": 0},
            "bonds":      {"invested": 2_85_000,  "current": 2_85_000,  "returns": 0},
            "crypto":     {"invested": 65_000,    "current": 1_00_500,  "returns": 35_500},
            "commodities":{"invested": 4_41_250,  "current": 5_92_600,  "returns": 1_51_350},
            "us_stocks":  {"invested": 5_98_625,  "current": 12_06_400, "returns": 6_07_775},
        },
        total_invested=Decimal("40_35_125"),
        total_current_value=Decimal("50_61_400"),
        total_returns=Decimal("10_26_275"),
        money_added_this_month=Decimal("14_500"),
        returns_this_month=Decimal("22_000"),
    )
)
say("Monthly snapshot for March 2025 created")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("✅  Seed complete! Login at http://localhost:8000")
print()
print("   Username   Password      Role")
print("   ─────────  ────────────  ──────────────────────")
print("   atul       password123   Primary Account Holder (admin)")
print("   spouse     password123   Account Holder")
print("   landlord   password123   Landlord")
print()
print("   Portfolio password: portfolio123")
print("   pgAdmin:            http://localhost:5050  (admin@vault.local / admin)")
print("═" * 60 + "\n")
