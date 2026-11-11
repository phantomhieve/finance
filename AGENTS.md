# AGENTS.md — Agent Engineering Handbook

Authoritative architecture, security, precision, and verification standards for AI coding agents working in **Vault** (`/Users/phantomhive/Desktop/GitHub/finance`).

Companion references:
- Quick-start index: [`GEMINI.md`](GEMINI.md)
- Deep domain & service map: [`.agents/skills/vault-architecture/SKILL.md`](.agents/skills/vault-architecture/SKILL.md)
- AI Gateway & DAG specification: [`docs/ux/0001-ai-calling-and-dag-strategy.md`](docs/ux/0001-ai-calling-and-dag-strategy.md)
- Design system & UI components: [`DESIGN.md`](DESIGN.md), [`docs/ux/IA.md`](docs/ux/IA.md), [`docs/ux/components.md`](docs/ux/components.md)
- Granular enforcement rules: [`.agents/rules/`](.agents/rules/)

---

## 1. System Topology & App Boundaries

Vault is a household-scoped wealth management and expense intelligence platform built on **Django 6.0**, **Python 3.12+**, **Starlette ASGI**, **Tailwind CSS v4 (`@tailwindcss/browser@4`) + DaisyUI 5**, **Chart.js 4**, **Unfold Admin**, and **FastMCP**.

```text
                         ┌────────────────────────────────────────┐
                         │           pftracker/asgi.py            │
                         └──────────────────┬─────────────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │                                               │
             HTTP Requests (/...)                            SSE Stream (/mcp)
                    │                                               │
         ┌──────────▼──────────┐                         ┌──────────▼──────────┐
         │ Django Applications │                         │     mcp_server      │
         └──────────┬──────────┘                         │  (OAuth 2.0 PKCE +  │
                    │                                    │   FastMCP Server)   │
      ┌─────────────┼─────────────┬─────────────┐        └──────────┬──────────┘
      │             │             │             │                   │
┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐             │
│  tracker  │ │ portfolio │ │ expenses  │ │ jewellery │             │
└───────────┘ └───────────┘ └───────────┘ └───────────┘             │
      │             │             │             │                   │
      └─────────────┴──────┬──────┴─────────────┴───────────────────┘
                           │
             ┌─────────────▼─────────────┐
             │    Unified AI Gateway     │
             │ (pftracker/ai_gateway/)   │
             │   Quant-Grounded AI DAGs  │
             └───────────────────────────┘
```

- **`pftracker/`**: Project settings, dual ASGI router (`asgi.py`), unified AI gateway (`ai_gateway/`), safe thread/async DB pools (`concurrency.py`), SQLite WAL PRAGMAs (`db_optimizations.py`), household context processor (`context_processors.py`), and shared Indian FY / `Decimal` helpers (`utils.py`).
- **`tracker/`**: Multi-tenancy (`User`, `AccountGroup`, `HouseholdConfig`), April–March Monthly Savings vs. Goals ledger, HRA Rent Tracker, Personal Notes/To-Dos, and `WebAuthnCredential`.
- **`portfolio/`**: 11-asset-class wealth engine (Indian Stocks, Mutual Funds, US RSUs, EPF, PPF, NPS, Fixed Deposits, Cash, Bonds, Crypto, Gold/Silver, Real Estate), Google Sheets sync & live rate fetchers (`services.py`), Indian rupee template filters (`templatetags/indian_format.py`), and multi-stage AI DAGs (`dag.py`, `land_appraisal.py`, `ai/`).
- **`expenses/`**: Gmail OAuth 2.0 multi-inbox sync (`gmail.py`, `sync.py`), bank/UPI parsers (`parsing.py`), encrypted PDF statement 3-stage reconciliation (`statements.py`, `crypto.py`), dual-leg transfer settlement (`ingestion.py`), EMI tracking (`emi.py`), 4-tier categorization (`categories.py`), net-spend analytics (`analytics.py`), and AI operations (`ai/`, `anomaly.py`).
- **`jewellery/`**: Precious metal & ornament custody ledger (`BANK_LOCKER` vs. `HOME_SAFE`), fineness-adjusted live bullion valuation, UUID-isolated photo storage, and WebP thumbnail caching (`utils.py`).
- **`mcp_server/`**: FastMCP SSE server exposing 30+ read/write financial tools with OAuth 2.0 PKCE (`oauth.py`), `PRIMARY` role & scope guard (`middleware.py`), and reversible `MCPAuditLog` snapshots (`audit.py`).

---

## 2. Multi-Tenancy, Access Control & Secrets

1. **Tenant Isolation (`AccountGroup`)**:
   - **User-scoped (`tracker`)**: `Category`, `Transaction`, `HRAExpense`, `FinancialGoal`, `GoalIncrement`, `MonthlyGoalAdjustment`, `Note`, `MonthlySavingsComment`, and `WebAuthnCredential` filter by resolved household owner or `group_user_filter(request.user)`.
   - **Group-scoped (`portfolio`, `jewellery`, `expenses`, `mcp_server`)**: Filter strictly by `group=request.user.group` (and `_gf(group)` fail-closed `{"id__in": []}` when `group is None`). Never query across households on PK alone.
2. **Role Enforcement (`tracker.User.user_type`)**:
   - `PRIMARY`: Full access across all modules, investments, real estate, and `/mcp/sse`.
   - `ACCOUNT_HOLDER`: View-only Savings, full HRA, read-only Jewellery catalog (valuations & CRUD restricted to `PRIMARY`), Notes, and Expenses (**`Investments` category masked** via `_hides_investments(request)`). Portfolio and MCP return `403 Forbidden`.
   - `LANDLORD`: View-only access restricted strictly to `/hra/`.
3. **Vault Session Gates & Mutations**:
   - Portfolio and Jewellery routes enforce `_vault_gate` (`30-minute` password or WebAuthn passkey TTL, `5`-attempt / `5`-minute cache lockout). Expenses enforces `EXPENSES_UNLOCK_TTL` (`4-hour` default) when a household vault password is set.
   - All state-changing HTTP endpoints MUST use `@require_POST` + CSRF protection, and login/`next` redirects MUST validate `url_has_allowed_host_and_scheme`.
4. **Secrets Prohibition**:
   - Enforced by `.agents/scripts/safety_pre_tool.py` and [`.agents/rules/no-secrets.md`](.agents/rules/no-secrets.md). Never read, grep, echo, or commit `.env`, `scripts/DEPLOY.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, or service-account JSONs. Inspect `.env.example`, `scripts/DEPLOY.env.example`, `portfolio/investor_profile.md.example`, and `pftracker/settings.py` instead. Never delete `portfolio/investor_profile.md` (loaded at runtime by `portfolio/dag.py`).

---

## 3. Financial Precision & Indian Fiscal Standards

- **`Decimal` Exclusively**: Use `decimal.Decimal` for all currency amounts, quantities, weights, and interest rates. Convert to `float` only at terminal Chart.js JSON serialization or transient CAGR exponentiation before quantizing back to `Decimal('0.01')`. Use `pftracker.utils.pct` and `pnl_pct` for percentage math.
- **Indian Financial Year (April 1 – March 31)**: January–March dates belong to the prior calendar year's FY (e.g., Feb 2026 -> `FY 2025-26`). Use `fy_start_year(date)` and `fy_label(fy_start)` from `pftracker.utils`.
- **Indian Currency Formatting**: Load `{% load indian_format %}` (`portfolio/templatetags/indian_format.py`) and format figures with `|inr` (`₹12,50,000`), `|inr_short` (`₹12.5 L`, `₹1.24 Cr`), or `|indian_number` (`12,50,000`), paired with `font-variant-numeric: tabular-nums`.

---

## 4. Database, Concurrency & AI Gateway Standards

- **Anti-N+1 & Write Safety**: Always attach `.select_related()` / `.prefetch_related()` when iterating relations, use `bulk_create` / `bulk_update` for batch writes, and pass `update_fields=[...]` on partial `.save()` calls.
- **Safe Worker Concurrency**: Offload parallel threads exclusively through `DjangoSafeThreadPoolExecutor`, `parallel_map`, or `safe_async_to_thread` (`pftracker/concurrency.py`) so worker DB connections are cleaned up deterministically.
- **AI Tiering & Quant-First DAGs (`pftracker/ai_gateway/`)**:
  - Production deep reasoning and search tasks (`PORTFOLIO_INSIGHTS`, `PORTFOLIO_DAG_STRATEGY`, `PORTFOLIO_DAG_SYNTHESIS`, `LAND_APPRAISAL_*`) run on **`gemini-4-carbon`** (`ThinkingLevel.HIGH` in prod, `ThinkingLevel.LOW` in dev).
  - Specialist Stage 1 lenses and expense extraction/classification tasks (`PORTFOLIO_DAG_ALLOCATION/QUALITY/MACRO`, `EXPENSE_*`, `RECEIPT_*`, `STATEMENT_*`) run on **`gemini-3.8-flash`** in prod (`gemini-2.5-flash-lite` in dev) with `thinking_budget=0`.
  - Pre-compute exact `Decimal` metrics in Python before calling LLMs, wrap untrusted text via `use_boundary_tags=True` (per-call random-nonced `<user_payload_<hex>>`), and maintain portfolio/asset-grounded fallbacks on every DAG stage. See [`docs/ux/0001-ai-calling-and-dag-strategy.md`](docs/ux/0001-ai-calling-and-dag-strategy.md).

---

## 5. CodeGraph Navigation & Pre-Push Verification

1. **Query CodeGraph First**: Prefer `codegraph_query`, `codegraph_node`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`, and `codegraph_affected` (or `codegraph <cmd>`) over blind text searches. Run `codegraph impact <symbol>` before changing shared signatures.
2. **Pre-Commit / Pre-Push Checks** (all mandatory):
   ```bash
   ./venv/bin/ruff check --select F,E9 .
   ./venv/bin/python manage.py check --fail-level WARNING
   ./venv/bin/python manage.py test --keepdb
   codegraph sync
   ```
3. **Conventional Commits**: Format `<type>(<scope>): <imperative summary>` (`feat`, `fix`, `perf`, `refactor`, `test`, `chore`, `docs`; scopes: `pftracker`, `tracker`, `portfolio`, `expenses`, `jewellery`, `mcp`, `ui`, `agents`, `docs`) with a clear motivation paragraph and bulleted change list.
