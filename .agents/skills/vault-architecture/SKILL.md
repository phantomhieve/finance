---
name: vault-architecture
description: Architectural guide, domain model map, security invariants, AI Gateway & DAG pipeline architecture, and UI/UX conventions for the Vault Personal Finance & Portfolio Tracker (Django 6.0).
---

# Vault Architecture & Domain Skill

Read this skill before designing features, modifying business logic, writing database queries, or auditing security across the Vault repository.

---

## 1. System Overview & App Boundaries

Vault is a multi-tenant, household-scoped personal finance, expense intelligence, and wealth management platform built for the Indian financial ecosystem (**Django 6.0**, **Python 3.12+**, **Tailwind CSS v4 (`@tailwindcss/browser@4`) + DaisyUI 5**, **Chart.js 4**, **Unfold Admin**, **FastMCP**).

| App / Package | Responsibility | Key Entry Points |
| :--- | :--- | :--- |
| **`pftracker/`** | Project settings, dual ASGI router (`/mcp` vs. Django HTTP), OAuth 2.0 discovery, DB pooling/concurrency, and the **Unified AI Gateway** (`pftracker/ai_gateway/`). | `pftracker/settings.py`, `pftracker/asgi.py`, `pftracker/urls.py`, `pftracker/concurrency.py`, `pftracker/ai_gateway/gateway.py` |
| **`tracker/`** | Custom `User` & `AccountGroup` multi-tenancy, `HouseholdConfig` feature flags, FY Monthly Savings vs. Goals, HRA Tracker, Personal Notes/To-Dos, and `WebAuthnCredential`. | `tracker/models.py`, `tracker/services.py`, `tracker/views.py` |
| **`portfolio/`** | 11-asset-class wealth engine (Stocks, Mutual Funds, US RSUs, EPF, PPF, NPS, FDs, Cash, Bonds, Crypto, Gold/Silver, Real Estate), Master vs. Child (`is_baby`) split, Google Sheets sync, live bullion/FX rates, `indian_format` filters, and **Quant-Grounded Portfolio & Land AI DAGs**. | `portfolio/models.py`, `portfolio/services.py`, `portfolio/views.py`, `portfolio/dag.py`, `portfolio/land_appraisal.py`, `portfolio/ai/` |
| **`expenses/`** | Automated household expense tracker: Gmail OAuth 2.0 alert sync (30+ Indian banks), credit card PDF statement unlocking & 3-stage reconciliation, dual-leg transfer settlement, EMI tenure tracker, refund netting, subscription cadence matrix, and AI forensic anomaly auditing. | `expenses/models.py`, `expenses/services.py`, `expenses/views.py`, `expenses/analytics.py`, `expenses/ingestion.py`, `expenses/categories.py`, `expenses/statements.py`, `expenses/parsing.py`, `expenses/ai/` |
| **`jewellery/`** | Physical precious metal & ornament custody ledger (`BANK_LOCKER` vs. `HOME_SAFE`), fineness-adjusted live valuation, UUID-isolated photo storage, and cached WebP thumbnails. | `jewellery/models.py`, `jewellery/views.py`, `jewellery/utils.py` |
| **`mcp_server/`** | FastMCP SSE server exposing 30+ read/write financial tools to external AI clients (Claude, ChatGPT, Cursor) with OAuth 2.0 PKCE, scope enforcement, and reversible `MCPAuditLog` snapshots. | `mcp_server/server.py`, `mcp_server/middleware.py`, `mcp_server/oauth.py`, `mcp_server/audit.py` |

---

## 2. Multi-Tenancy, Access Control & Security Invariants

### 2.1 Tenant Scoping (`User` vs. `AccountGroup`)
- **User-Scoped Models (`tracker`)**: `Category`, `Transaction`, `HRAExpense`, `FinancialGoal` (monthly savings goal), `GoalIncrement`, `MonthlyGoalAdjustment`, `Note`, `MonthlySavingsComment`, and `WebAuthnCredential` filter by `group_user_filter(user)` (`tracker/services.py`) so household members view shared household records while edit mutations remain gated by role.
- **Group-Scoped Models (`portfolio`, `jewellery`, `expenses`, `mcp_server`)**: All models filter strictly by `group=request.user.group`.
- **Fail-Closed Group Filter (`_gf`)**:
  - `_gf(group)` returns `{"id__in": []}` when `group is None` (never `{}`), preventing an unassigned user from querying across tenants.
  - Always pass `group=group` into `.filter()`, `.get()`, and `get_object_or_404()` calls on group-scoped models.

### 2.2 Role Matrix (`tracker.User.user_type`)

| Capability / Guard | `PRIMARY` | `ACCOUNT_HOLDER` (Spouse/Partner) | `LANDLORD` |
| :--- | :---: | :---: | :---: |
| **Savings Dashboard (`can_view_savings`)** | View + Edit (`can_edit_savings`) | View Only | Blocked (Redirects to `/hra/`) |
| **HRA & Rent Tracker (`can_edit_hra`)** | View + Edit | View + Edit | View Only |
| **Expenses (`can_view_expenses`)** | Full Access (incl. `Investments` category) | Full Access (**`Investments` category masked**) | Blocked |
| **Jewellery (`can_view_jewellery`)** | View + Edit (requires `_vault_gate`) | View Only — valuations & CRUD hidden (requires `_vault_gate`) | Blocked |
| **Portfolio (`can_view_portfolio`)** | Full Access (requires `_vault_gate`) | Blocked | Blocked |
| **MCP Server (`/mcp/sse`)** | Allowed (`read` / `write` OAuth scopes) | Blocked (`403 Forbidden`) | Blocked (`403 Forbidden`) |

### 2.3 Investment Category Masking (`_hides_investments`)
- Household members with `can_view_portfolio == False` (`ACCOUNT_HOLDER`) share the household's `expenses` module while all expenses, totals, and merchant rules in `'Investments'` (`INVESTMENT_CATEGORY`) are excluded via `_hides_investments(request)` in `expenses/views.py` and `hide_investments=True` on `month_summary` / `fy_summary`.

### 2.4 Vault Gate (`_vault_gate`) & WebAuthn Biometrics
- Sensitive views in `portfolio` and `jewellery` enforce `_vault_gate` (`30-minute` rolling unlock TTL when `group.portfolio_password` is configured); `expenses` enforces `EXPENSES_UNLOCK_TTL` (`4-hour` default via `EXPENSES_UNLOCK_TTL_SECONDS`).
- **Brute-Force Protection**: `portfolio_unlock` (`portfolio/views.py`) enforces a `5`-attempt / `5`-minute lockout per `(group_id, client_ip)` using `vault_unlock_*` keys in Django's cache.
- **WebAuthn Single-Use Challenges**: `webauthn_register_complete` and `webauthn_auth_complete` consume challenges via `request.session.pop(...)` so challenges cannot be replayed.

### 2.5 Encryption at Rest (`expenses/crypto.py`)
- Uses Fernet symmetric encryption keyed by `EXPENSES_ENCRYPTION_KEY` (falling back to `SHA-256('vault-expenses:' + SECRET_KEY)` when unset; short-lived Gmail access tokens stay in-memory on `GmailClient`) to encrypt:
  - `GmailAccount.refresh_token_enc`
  - `PaymentSource.statement_password_enc`
  - `CardStatement.pdf_blob`
  - `HouseholdConfig.google_credentials_json`

---

## 3. Financial Computation & Indian Ecosystem Standards

1. **Precision**: Use `decimal.Decimal` exclusively for currency, weights, interest rates, and percentages (`pftracker.utils.pct`, `pnl_pct`). Convert to `float` only transiently for exponentiation in CAGR/FD compounding or terminal Chart.js JSON serialization, quantizing back to `Decimal('0.01')`.
2. **Indian Financial Year (Apr–Mar)**:
   - FY `Y` spans **April 1, `Y`** to **March 31, `Y+1`** (`fy = d.year if d.month >= 4 else d.year - 1`; helpers `fy_start_year`, `fy_label` in `pftracker.utils`).
3. **Number Formatting**: Load `{% load indian_format %}` (`portfolio/templatetags/indian_format.py`) using `|inr`, `|inr_short`, and `|indian_number` in templates, and `formatINR` / `formatINRShort` in `static/js/vault-utils.js`.
4. **North Indian Real Estate Units (`RealEstateHolding`)**:
   - Normalizes `GAJ` (`1 Gaj = 1 Sq. Yard = 9 Sq. Ft`), `SQFT`, `SQYD`, `ACRE` (`4,840 Gaj`), `BIGHA` (`~1,008 Gaj`), and `SQMT` via `holding.area_in_gaj`; `total_cost_basis = purchase_price + stamp_duty_charges`.

---

## 4. Expense Intelligence Architecture (`expenses/`)

- **`expenses/categories.py`**: 4-tier categorization waterfall (`Household MerchantRule` -> `BrandKnowledge / KeywordKnowledge` -> `Channel Heuristics` -> `ai_categorise_pending` with canonical `(merchant_signature, direction, channel)` deduplication inside `expenses/ai/runner.py`).
- **`expenses/ingestion.py` & `expenses/views.py`**: `build_expense` normalizes merchants, masks sensitive tokens, resolves `PaymentSource`, and enforces idempotency (`dedupe_key`); `settle_internal_movements` pairs internal bank/card transfers (`SETTLE_WINDOW_DAYS = 3`), and `_collapse_transfer_legs` collapses paired legs in $O(C)$ time into a unified `Bank -> Card` row.
- **`expenses/statements.py`**: Unlocks encrypted PDFs (`pypdf`, `MAX_PDF_BYTES = 10 MB`, `MAX_PDF_PAGES = 40`), extracts multi-chunk statement lines in parallel (`DjangoSafeThreadPoolExecutor`), and runs **3-Stage Statement Reconciliation** (Rule Match -> AI Candidate Disambiguation -> Auto-Add & Refund Pairing).
- **`expenses/analytics.py`**: Computes net spend (subtracting `refunded_amount` and standalone refund credits), Fixed vs. Discretionary splits, burn pace, and the 12-month `subscription_summary` cadence matrix.

---

## 5. Unified AI Gateway & Quant-Grounded DAGs

Full specification: [`docs/ux/0001-ai-calling-and-dag-strategy.md`](../../../docs/ux/0001-ai-calling-and-dag-strategy.md).

- **Unified AI Gateway (`pftracker/ai_gateway/`)**:
  - `AIConfigRegistry` maps each `TaskProfile` to environment-aware models: **`gemini-4-carbon`** (`ThinkingLevel.HIGH` in prod) for `PORTFOLIO_INSIGHTS`, `PORTFOLIO_DAG_STRATEGY`, `PORTFOLIO_DAG_SYNTHESIS`, and `LAND_APPRAISAL_*`; **`gemini-3.8-flash`** (`thinking_budget=0` in prod; `gemini-2.5-flash-lite` in dev) for `PORTFOLIO_DAG_ALLOCATION/QUALITY/MACRO` and `EXPENSE_*`/`RECEIPT_*`/`STATEMENT_*`.
  - Enforces outbound Indian PII scrubbing (`mask_pii`), log secret redaction (`mask_secrets`), unconditional prompt-injection detection + per-call random-nonced `<user_payload_<hex>>` XML wrapping (`use_boundary_tags=True`), per-key HTTP 429 cooldowns, and cross-provider cascade failover (`gemini-cloud` <-> `shakti-primary`).
- **Portfolio Multi-Stage DAG (`portfolio/dag.py`)**:
  - **Stage 0**: Python `Decimal` Quant Engine computes full-universe HHI, tail losers (`<=-15%`), 3-tier liquidity vs. 6-month emergency floor, FD post-tax vs. `8.15%` EPF hurdle, `-35%` equity / `-30%` RSU crash drawdowns, Section 112A harvestable LTCG, and goal shortfalls.
  - **Stage 1**: Parallel `AllocationLensResult`, `QualityLensResult` (`list[LegacyFundAuditItem]`), and `MacroStressLensResult` on `gemini-3.8-flash` (`DjangoSafeThreadPoolExecutor` / `asyncio.gather`) with bounded `stage_timeout` and `Decimal`-grounded per-node fallbacks.
  - **Stage 2 & Stage 3**: `StrategyLensResult` and executive synthesis on `gemini-4-carbon` (`HIGH`), finalized by a deterministic Critic/Reducer enforcing $S = \text{round}(0.30 S_{\text{alloc}} + 0.25 S_{\text{qual}} + 0.25 S_{\text{strat}} + 0.20 S_{\text{macro}})$.
- **Land Appraisal DAG (`portfolio/land_appraisal.py`)**:
  - Combines Google Search-grounded Stage 1 discovery (`LAND_APPRAISAL_COMPS`), deterministic `Decimal` fiduciary haircuts (`SAH = 30%`, `IFD = max(15%, 9% + 0.75 * Repo)`, `ESP`, Macro Cap `Repo + CPI + 3%`), and code-clamped Stage 3 synthesis (`0% <= pct <= min(15%, macro_cap, auditor_ceiling)`).

---

## 6. Private Bank Folio UI & Concurrency Architecture

- **Frontend (`DESIGN.md`, `static/css/style.css`, `templates/base.html`)**:
  - Tailwind CSS v4 (`@tailwindcss/browser@4`) + DaisyUI 5 (`night` `#0b0f17` ground / `#111722` sheet; `winter` `#f8fafc` ground / `#ffffff` sheet; `localStorage.getItem('vault-theme')`) + Chart.js 4 (`vault:themechange` sync) + Material Symbols Outlined.
  - Desktop collapsible rail (`aside#desktopSidebar`) + sticky `header.v-topbar`; mobile 5-slot `nav.v-mobile-dock` + `#mobileNavDrawer` + bottom-sheet `<dialog>` modals (`<768px`) with `>=44x44px` hit targets.
  - Every state mutation uses `<form method="post">{% csrf_token %}</form>` and `@require_POST`.
- **Database & Safe Concurrency (`pftracker/settings.py`, `db_optimizations.py`, `concurrency.py`, `asgi.py`)**:
  - Production `CONN_MAX_AGE=600` (`0` in dev/tests) with `CONN_HEALTH_CHECKS=True`; SQLite WAL mode with `15s` busy timeout and `64MB` page cache.
  - `DjangoSafeThreadPoolExecutor` and `DatabaseConnectionLifecycleMiddleware` guarantee leak-free DB connections across worker threads and `/mcp` ASGI streams; composite indexes cover all `is_baby` and `AccountGroup` holding lookups.

---

## 7. Pre-Push Verification Checklist

```bash
./venv/bin/ruff check --select F,E9 .
./venv/bin/python manage.py check --fail-level WARNING
./venv/bin/python manage.py test --keepdb
codegraph sync
```
