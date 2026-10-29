---
name: vault-architecture
description: Comprehensive architectural guide, domain model map, security invariants, AI pipeline architecture, and UI/UX conventions for the Vault Personal Finance & Portfolio Tracker (Django 6.0).
---

# Vault Architecture & Domain Skill

Read this skill before designing features, modifying business logic, writing database queries, or auditing security across the Vault repository.

---

## 1. System Overview & App Boundaries

Vault is a multi-tenant, household-scoped personal finance, expense intelligence, and wealth management platform built for the Indian financial ecosystem (**Django 6.0**, **Python 3.12+**, **Tailwind CSS v4 + DaisyUI 5**, **Chart.js 4**, **FastMCP**).

| App / Package | Responsibility | Key Entry Points |
| :--- | :--- | :--- |
| **`pftracker/`** | Project settings, ASGI dual-router (`/mcp/sse` vs Django HTTP), OAuth 2.0 discovery, and the **Unified AI Gateway** (`pftracker/ai_gateway/`). | `pftracker/settings.py`, `pftracker/asgi.py`, `pftracker/urls.py`, `pftracker/ai_gateway/gateway.py` |
| **`tracker/`** | Custom `User` & `AccountGroup` multi-tenancy, `HouseholdConfig` feature flags, FY Monthly Savings vs Goals, HRA Tracker, Personal Notes/To-Dos, and `WebAuthnCredential`. | `tracker/models.py`, `tracker/views.py`, `tracker/context_processors.py` |
| **`portfolio/`** | Multi-asset wealth engine (Stocks, Mutual Funds, US RSUs, EPF, NPS, FDs, Cash, Bonds, Crypto, Gold/Silver, Real Estate), Master vs Child (`is_baby`) split, Google Sheets sync, live price fetchers, and **Multi-Stage AI DAG Engine**. | `portfolio/models.py`, `portfolio/views.py`, `portfolio/dag.py`, `portfolio/ai.py`, `portfolio/sheets_sync.py`, `portfolio/price_service.py` |
| **`expenses/`** | Automated household expense tracker: Gmail OAuth 2.0 alert sync (30+ Indian banks), credit card PDF statement unlocking & 3-stage reconciliation, dual-leg transfer settlement, EMI tenure tracker, refund netting, subscription cadence matrix, and AI forensic anomaly auditing. | `expenses/models.py`, `expenses/services.py`, `expenses/views.py`, `expenses/analytics.py`, `expenses/ingestion.py`, `expenses/categories.py`, `expenses/statements.py`, `expenses/parsing.py` |
| **`jewellery/`** | Physical precious metal & ornament inventory (`BANK_LOCKER` vs `HOME_SAFE`), fineness-adjusted live valuation, UUID-isolated photo storage, and cached WebP thumbnails. | `jewellery/models.py`, `jewellery/views.py`, `jewellery/utils.py` |
| **`mcp_server/`** | FastMCP SSE server exposing 30+ read/write financial tools to external AI clients (Claude, ChatGPT, Cursor) with OAuth 2.0 PKCE, scope enforcement, and reversible `MCPAuditLog` snapshots. | `mcp_server/server.py`, `mcp_server/middleware.py`, `mcp_server/models.py` |

---

## 2. Multi-Tenancy, Access Control & Security Invariants

### 2.1 Tenant Scoping (`User` vs `AccountGroup`)
- **User-Scoped Models (`tracker`)**: `Category`, `Transaction`, `HRAExpense`, `FinancialGoal` (monthly savings goal), `GoalIncrement`, `MonthlyGoalAdjustment`, `Note`, `MonthlySavingsComment`, and `WebAuthnCredential` filter by `user=target_user`.
  - When an `ACCOUNT_HOLDER` or `LANDLORD` views savings/HRA, `_get_savings_owner(request.user)` resolves the household's `PRIMARY` user in the same `AccountGroup` so shared household data is displayed while respecting edit permissions.
- **Group-Scoped Models (`portfolio`, `jewellery`, `expenses`, `mcp_server`)**: All models filter by `group=request.user.group`.
- **Fail-Closed Group Filter (`_gf`)**:
  - In `portfolio/views.py`, `_gf(group)` **must** return `{"id__in": []}` when `group is None` (never `{}`), preventing an unassigned user from querying across tenants.
  - Always pass `group=group` into every `.filter()`, `.get()`, and `get_object_or_404()` call on group-scoped models.

### 2.2 Role Matrix (`tracker.User.user_type`)

| Capability / Guard | `PRIMARY` | `ACCOUNT_HOLDER` (Spouse/Partner) | `LANDLORD` |
| :--- | :---: | :---: | :---: |
| **Savings Dashboard (`can_view_savings`)** | View + Edit (`can_edit_savings`) | View Only | Blocked (Redirects to `/hra/`) |
| **HRA & Rent Tracker (`can_edit_hra`)** | View + Edit | View + Edit | View Only |
| **Expenses (`can_view_expenses`)** | Full Access (incl. `Investments` category) | Full Access (**`Investments` category masked**) | Blocked |
| **Jewellery (`can_view_jewellery`)** | View + Edit (requires `_vault_gate`) | View + Edit (requires `_vault_gate`) | Blocked |
| **Portfolio (`can_view_portfolio`)** | Full Access (requires `_vault_gate`) | Blocked | Blocked |
| **MCP Server (`/mcp/sse`)** | Allowed (`read` / `write` OAuth scopes) | Blocked (`403 Forbidden`) | Blocked (`403 Forbidden`) |

### 2.3 Investment Category Masking (`_hides_investments`)
- Household members with `can_view_portfolio == False` (e.g., `ACCOUNT_HOLDER`) share the household's `expenses` module but **must never see or modify** expenses or rules in the `'Investments'` category (`INVESTMENT_CATEGORY`).
- Views (`expenses_home`, `expenses_year`, `expenses_settings`, `expense_edit`, `expense_delete`, `statement_line_resolve`) and services (`learn_category`, `fy_summary`, `month_summary`) enforce `_hides_investments(request.user)` (`exclude_investments=True`).

### 2.4 Vault Gate (`_vault_gate`) & WebAuthn Biometrics
- Sensitive views in `portfolio` and `jewellery` call `_vault_gate(request)` before executing.
- If `group.portfolio_password` is configured, `request.session[f'portfolio_unlocked_{group.id}']` must be `True` (valid for 30 minutes).
- **Brute-Force Protection**: `_check_unlock_rate_limit(request, group)` and `_record_unlock_failure(request, group)` enforce a 5-attempt / 5-minute lockout per `(group_id, client_ip)` using Django's cache.
- **WebAuthn Single-Use Challenges**: `webauthn_register_complete` and `webauthn_auth_complete` consume challenges via `request.session.pop(...)` so challenges cannot be replayed.

### 2.5 Encryption at Rest (`expenses/crypto.py`)
- Uses Fernet symmetric encryption keyed by `VAULT_FERNET_KEY` (or HKDF-SHA256 derived from `SECRET_KEY`).
- Encrypts:
  - `GmailAccount.refresh_token_encrypted` & `access_token_encrypted`
  - `PaymentSource.pdf_password_encrypted`
  - `CardStatement.pdf_encrypted` (raw statement PDF binary)
  - `HouseholdConfig.google_credentials_json` (auto-encrypted in `HouseholdConfig.save()`)

---

## 3. Financial Computation & Indian Ecosystem Standards

1. **Precision**: Always use `decimal.Decimal` for currency, weights, interest rates, and percentages. Never use IEEE-754 `float` for storage or aggregation (only convert to `float` transiently for exponentiation in CAGR/FD compounding, then quantize back to `Decimal('0.01')`).
2. **Indian Financial Year (Apr–Mar)**:
   - FY `Y` spans **April 1, `Y`** to **March 31, `Y+1`** (e.g., `fy=2025` is `FY 2025-26`: `2025-04-01` to `2026-03-31`).
   - Date-to-FY resolution: `fy = d.year if d.month >= 4 else d.year - 1`.
3. **Number Formatting**: Use Indian numbering conventions (`₹1,23,456`, Lakhs `L`, Crores `Cr`) via `tracker/templatetags/indian_numbers.py` (`indian_comma`, `compact_inr`) and `Vault.fmtINR` in JS.
4. **North Indian Real Estate Units (`RealEstateHolding`)**:
   - Supports `GAJ` (`1 Gaj = 1 Sq. Yard = 9 Sq. Ft`), `SQFT`, `SQYD`, `ACRE` (`4,840 Gaj`), `BIGHA` (`~1,008 Gaj`), and `SQMT`.
   - `total_cost_basis = purchase_price + stamp_duty_charges`.

---

## 4. Expense Intelligence Architecture (`expenses/`)

### 4.1 Service Layer Facade (`expenses/services.py`)
`expenses/services.py` re-exports the modular domain functions from:
- **`expenses/categories.py`**:
  - Multi-tier categorization waterfall:
    1. **Household `MerchantRule`** (`source='USER'` -> confidence `1.0`, `source='AI'` -> cached rule).
    2. **Global Knowledge Catalog** (`BrandKnowledge` & `KeywordKnowledge` in `expenses/knowledge.py` + regex rules in `expenses/parsing.py`).
    3. **Channel & Direction Heuristics** (`ATM` -> `'Cash Withdrawal'`, credit card credits -> `'Credit Card Payment'`, other credits -> `'Income & Refunds'`).
    4. **AI Batch Categorization (`ai_categorise_pending`)**: Batches uncategorized merchants through the AI Gateway (`TaskType.FAST`); high-confidence (`>= 0.6`) results auto-populate both household `MerchantRule` and global `BrandKnowledge`.
- **`expenses/ingestion.py`**:
  - `build_expense`: Normalizes merchants (`normalize_merchant`), masks sensitive strings (`mask_sensitive`), resolves/auto-creates `PaymentSource`, and enforces idempotency via `dedupe_key`.
  - `settle_internal_movements(group, since)`: Automatically detects and refiles internal transfers (`SETTLE_WINDOW_DAYS = 3`) so money moving between household accounts is never double-counted as spend:
    - Pairs a bank debit (`Leg 1`) against a `CardStatement` paid/total amount or a credit card `CREDIT` row (`Leg 2`) -> refiles as `'Credit Card Payment'` (`category_source='MATCH'`).
    - Pairs equal opposite-direction entries across two household `PaymentSource` accounts -> refiles as `'Transfers'`.
- **`expenses/views.py` (`_collapse_transfer_legs`)**:
  - At feed render time, pairs bank debit (`Leg 1`) and credit card bill credit (`Leg 2`) within ±4 days (`kind in ('TRANSFER', 'BILL')`), hides the redundant credit leg from the feed, and attaches `paired_source` to the primary leg so the UI renders a unified `Bank -> Card` badge.
- **`expenses/statements.py`**:
  - Reads encrypted/password-protected credit card PDFs (`pypdf`, `MAX_PDF_BYTES = 10 MB`, `MAX_PDF_PAGES = 40`).
  - **3-Stage Statement Reconciliation**:
    1. **Rule Match**: Same card family (`card_family_ids`), amount within `₹1.00`, date within `±3 days`, merchant similarity threshold.
    2. **AI Disambiguation**: Plausible candidates within `±10 days` and `6%` amount ratio are evaluated by AI; ambiguous matches are parked with `needs_review=True`.
    3. **Auto-Add**: Unmatched statement lines are added as `STATEMENT` expenses; credits are reconciled as refunds (`reconcile_refunds`) against prior purchases.
- **`expenses/analytics.py`**:
  - **Net Spend Formula**: `spend_q()` filters `direction='DEBIT'`, `category__kind='SPEND'` (or uncategorized non-card credits). Net spend subtracts `F('refunded_amount')` on debit rows **and** standalone refund credits (`credit_refunds_q()`).
  - **`month_summary` & `fy_summary`**: Computes Fixed (`Rent`, `Utilities & Bills`, `EMI & Loans`, `Subscriptions`, `Insurance`, `Education`) vs Discretionary split, daily burn pace vs last month/year, category sparklines, top merchants, and payment mode share.
  - **`subscription_summary`**: Builds a 12-month `Apr–Mar` recurring cadence matrix across `Subscriptions` category items, multi-month `Utilities & Bills`, and known `SUBSCRIPTION_BRANDS`, computing monthly equivalent burn and annualized run-rate.

---

## 5. Unified AI Gateway & Portfolio DAG Engine

### 5.1 Unified AI Gateway (`pftracker/ai_gateway/`)
All LLM calls across `portfolio`, `expenses`, and `mcp_server` route through `pftracker.ai_gateway.gateway`:
- **Task Tiers (`TaskType`)**:
  - `FAST`: High-throughput categorization, statement line disambiguation (`llama3_3` / `gemini-2.5-flash`).
  - `REASONING`: Deep multi-pillar portfolio strategy & forensic expense auditing (`deepseek-r1` / `gemini-2.5-pro`).
  - `RESEARCH`: Live web-grounded market intelligence & weekly equity briefs (`gemini-2.5-flash` with Google Search grounding).
  - `EXTRACTION`: Unstructured email and PDF statement table extraction.
- **Resilience**: `NodeRouter` + `CircuitBreakerManager` handle priority failover, weighted round-robin across API key pools, 60s per-key cooldown on HTTP `429` rate limits, and JSON repair (`clean_json_text`, `safe_json_loads`) for reasoning models that emit `<think>` blocks.

### 5.2 Multi-Stage Portfolio DAG (`portfolio/dag.py`)
Replaces monolithic prompts with a 3-stage fan-out / fan-in workflow:
1. **Stage 1 (Parallel Diagnostic Lenses — `ThreadPoolExecutor`)**:
   - **Node 1A (`AllocationLensResult`)**: Asset mix vs age glide path, Herfindahl-Hirschman Index (HHI) concentration, 3-tier liquidity & 6-month emergency floor.
   - **Node 1B (`QualityLensResult`)**: Equity gainers/losers, legacy regular/sectoral Mutual Fund audit (`hold | merge | exit`), real estate micro-market yield, EPF tax-free hurdle comparison.
   - **Node 1C (`MacroStressLensResult`)**: Nifty 50 PE valuation regime, simulated `-35%` equity crash drawdown in ₹, tech/RSU correlation shock.
2. **Stage 2 (Tactical & Tax Synthesis — `StrategyLensResult`)**:
   - Synthesizes Stage 1 outputs into a cross-pillar rebalancing roadmap, goal shortfall SIP plan, and Indian FY tax-harvesting strategy (**Section 112A** ₹1.25L LTCG exemption, **Section 54 / 54EC** real estate capital gains rollover).
3. **Stage 3 (Deterministic Grounded Health Score & Terminal Curation)**:
   - Computes the grounded portfolio score deterministically:
     $$S_{\text{grounded}} = \text{round}(0.30 \cdot S_{\text{allocation}} + 0.25 \cdot S_{\text{quality}} + 0.25 \cdot S_{\text{strategy}} + 0.20 \cdot S_{\text{macro}})$$
   - Curates the final `PortfolioInsightsResponse` persisted in `PortfolioInsight`.

---

## 6. Frontend & Mobile-First UI/UX System

- **Stack**: Django Templates + **Tailwind CSS v4** (`static/css/src/input.css` -> `static/css/tailwind.out.css`) + **DaisyUI 5** (`light` / `dark` themes synced via `localStorage.getItem('vault_theme')`) + **Chart.js 4** + **Material Symbols Outlined**.
- **Navigation Shell (`templates/base.html`)**:
  - Desktop (`lg+`): Collapsible left sidebar (`aside#desktopSidebar`) with `Ctrl/Cmd + B` shortcut and persistent collapsed state (`vault_sidebar_collapsed`).
  - Mobile (`<lg`): Fixed bottom dock (`nav.dock`) with 5 primary destinations + slide-up sheet for secondary modules.
- **Mobile-First Bento Workspace Pattern**:
  - Complex pages (`expenses/home.html`, `expenses/year.html`, `expenses/settings.html`) use a sticky **Mobile Segmented Tab Bar** (`lg:hidden`) that toggles sections via `max-lg:hidden`, while desktop (`lg+`) displays the full multi-column Bento grid simultaneously.
  - Interactive rows use native `<dialog class="modal modal-bottom sm:modal-middle">` drawers for editing without full-page navigation clutter, paired with `Vault.saveScrollBeforeSubmit(form)` in `static/js/vault-core.js`.
- **CSRF & State Mutation Rule**:
  - **Never** mutate database state in a GET handler. Every state-changing action (deleting rows, toggling `is_baby`, toggling to-dos, unlocking statements, disconnecting Gmail) **must** use `<form method="post">{% csrf_token %}...</form>` and `@require_POST`.

---

## 7. Pre-Push Verification Checklist

Before committing or pushing any change:
1. **Build CSS** (if templates or `static/css/src/input.css` changed):
   ```bash
   npm run build:css
   ```
2. **Run Ruff Linter** (enforced by GitHub Actions CI):
   ```bash
   ./venv/bin/ruff check --select F,E9 .
   ```
3. **Run Full Test Suite**:
   ```bash
   ./venv/bin/python manage.py test expenses portfolio tracker jewellery mcp_server --keepdb
   ```
