---
name: vault-architecture
description: >-
  Provides deep domain architecture knowledge for Vault Personal Finance Dashboard,
  including multi-tenancy, user roles, security gates, financial year rules, and app boundaries.
---

# Vault Personal Finance — Architectural Reference

Vault is an Indian personal finance and investment management system built on Python 3.14 and Django 6.0, running asynchronously under Starlette/ASGI with Gunicorn and Uvicorn.

---

## 1. Multi-Tenancy & Authorization Model

### Household Grouping
- All core financial entities (`Transaction`, `ZerodhaAccount`, `FixedDeposit`, `CommodityHolding`, `JewelleryItem`, `Expense`, etc.) belong to an `AccountGroup`.
- Every `AccountGroup` has a 1-to-1 `HouseholdConfig` that controls module-level feature toggles (`feature_savings`, `feature_portfolio`, `feature_jewellery`, `feature_hra`, `feature_notes`, `feature_real_estate`, `feature_ai_insights`, `feature_expenses`).

### User Roles
- Defined in `tracker.models.User`:
  - `PRIMARY`: Full CRUD across all modules, including Portfolio, Jewellery, Admin monitoring, and MCP access.
  - `ACCOUNT_HOLDER`: Can view/manage Savings, Expenses, Jewellery, HRA, and Notes. Investment portfolio and investment-tagged expenses are strictly hidden.
  - `LANDLORD`: View-only access strictly restricted to HRA rent records.

### Vault Security Gate
- Portfolio and Jewellery views are protected by the `_vault_gate` decorator (`portfolio.views._vault_gate`).
- Requires entering the household's `portfolio_password` or authenticating via biometric WebAuthn (`WebAuthnCredential`).
- Successful authentication grants a session-bound access token with a 30-minute TTL (`_PORTFOLIO_UNLOCK_TTL = 1800`).

---

## 2. Core Modules Summary

### `pftracker` (Project Root & ASGI Gateway)
- `pftracker.asgi`: Starlette router dispatching `/mcp` to the Model Context Protocol app and `/` to Django.
- `pftracker.settings`: Unfold dark admin (`/vault-manage/`), CSP policies, session lifetime (8 hours, save every request).
- `pftracker.utils`: Standard Indian FY helpers (`fy_start_year`, `fy_label`, `fy_start_from_label`), precision math, Google credentials resolver.

### `tracker` (Monthly Savings, HRA & Notes)
- Fiscal Year (Apr 1 – Mar 31) savings tracking.
- Goal hierarchy: Base Annual Goal (`FinancialGoal`) + Step-up increments (`GoalIncrement`) + Month-specific adjustments (`MonthlyGoalAdjustment`).
- HRA tracking: Rent paid, landlord receipts, expense balance calculation.
- Personal notes: FY-linked notes, pending credits/debits, todo items.

### `portfolio` (Investments & Wealth)
- Asset classes: Stocks, Index MFs, Other MFs (synced from Google Sheets), EPF, NPS, Fixed Deposits (with compound interest calculation), Cash, Bonds, Crypto, Commodities (live rates via goodreturns.in scraper), US Stocks/RSUs, Real Estate (North Indian land units: Gaj, Sq. Yards, Sq. Ft, Bigha, Acres).
- Segmentation: `is_baby=True` segregates holdings into a dedicated child portfolio ("Advay portfolio") vs master portfolio.
- AI Analysis: Gemini integration using `google-genai` and Pydantic structured output, subject to a 30-day cooldown (`InsightGenerationSettings`).
- Automated snapshots: `MonthlySnapshot` captured on the 1st of every month.

### `jewellery` (Precious Metals Vault)
- Category & metal taxonomy (Gold, Silver, Platinum, Diamond/Other).
- Live valuation based on current `CommodityPrice` and purity multipliers.
- Secure photo uploads with HEIC/HEIF conversion and opaque UUID filenames.

### `expenses` (Automated Expense Tracker)
- Connected Gmail accounts (`gmail.readonly`) with Fernet-encrypted refresh tokens.
- Deterministic regex parser for 30+ Indian banks + fallback to Gemini LLM.
- Credit card statement PDF parser (`pypdf`) with encrypted password storage and reconciliation.
- Anomaly detection via median + MAD statistics.

### `mcp_server` (Model Context Protocol Integration)
- Standardized MCP server exposing read resources and write tools.
- OAuth 2.0 PKCE authentication with user-bound token validation.
- Complete mutation audit trail in `MCPAuditLog` with instant before/after JSON rollback.

---

## 3. Financial Computation Rules

1. **Precision Math**: Never use floating-point types for currency or holdings. Always use `Decimal` with `.quantize(Decimal('0.01'))` or `.quantize(Decimal('0'))`.
2. **Indian FY Cycle**: FY runs April 1 to March 31. A date in Jan–Mar 2026 belongs to FY 2025-26 (`fy_start_year = 2025`).
3. **P&L Definition**: `pnl = current_value - purchase_value`. Percentage returns use `pct = (pnl / purchase_value * 100).quantize(Decimal('0.01'))`.
