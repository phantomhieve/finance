# AGENTS.md — Antigravity Agent Guidelines & System Architecture

This is the primary developer and agent guide for the **Vault Personal Finance & Portfolio Tracker** codebase.
All agents operating in this repository MUST read and adhere to these guidelines.

For complete domain architecture and data models, also refer to:
- [`GEMINI.md`](GEMINI.md)
- [`.agents/skills/vault-architecture/SKILL.md`](.agents/skills/vault-architecture/SKILL.md)
- [`.agents/rules/`](.agents/rules/)

---

## 1. System Topology & App Boundaries

Vault is a multi-tenant, household-scoped wealth intelligence and personal finance engine built with **Django 6.0**, **Python 3.14**, **Starlette ASGI**, **Tailwind CSS v4 + DaisyUI 5**, **Chart.js 4**, and **FastMCP**.

```
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
             │   Multi-Stage AI DAGs     │
             └───────────────────────────┘
```

### Module Responsibilities:
- **`pftracker/`**: Project settings, ASGI dual-router, unified AI gateway (`ai_gateway/`), safe concurrency utilities (`concurrency.py`), SQLite WAL / database optimizations (`db_optimizations.py`), and shared financial helpers (`utils.py`).
- **`tracker/`**: Core multi-tenancy (`User`, `AccountGroup`, `HouseholdConfig`), Indian FY Monthly Savings vs Goals pacing, HRA Rent Tracker, Personal Notes & To-Dos, and WebAuthn credentials.
- **`portfolio/`**: Multi-asset portfolio engine (Indian Stocks, Mutual Funds, US RSUs, EPF, NPS, Fixed Deposits, Cash, Bonds, Crypto, Physical Gold/Silver, Real Estate), Google Sheets sync, live price scrapers, and the Multi-Stage DAG Workflow Engine (`dag.py`, `land_appraisal.py`).
- **`expenses/`**: Automated expense intelligence, Gmail OAuth 2.0 synchronization (30+ Indian banks), credit card PDF statement unlocking & 3-stage reconciliation, dual-leg transfer settlement, EMI amortization tracking, refund netting, and AI anomaly auditing.
- **`jewellery/`**: Physical precious metal & ornament inventory (`BANK_LOCKER` vs `HOME_SAFE`), live fineness-adjusted valuation, UUID-isolated photo storage, and WebP thumbnail caching.
- **`mcp_server/`**: Starlette ASGI FastMCP server exposing 30+ read/write financial tools to external AI assistants with OAuth 2.0 PKCE, scope gating, and reversible `MCPAuditLog` snapshots.

---

## 2. Multi-Tenancy & Security Invariants

### 2.1 User Scoping vs Group Scoping
- **User-Scoped Models (`tracker`)**: `Transaction`, `HRAExpense`, `FinancialGoal` (monthly goal), `GoalIncrement`, `MonthlyGoalAdjustment`, `Note`, `MonthlySavingsComment`, and `WebAuthnCredential` filter by `user=request.user` or `group_user_filter(request.user)`.
- **Group-Scoped Models (`portfolio`, `jewellery`, `expenses`, `mcp_server`)**: Models filter strictly by `group=request.user.group`.
- **Fail-Closed Filtering (`_gf`)**:
  - Never evaluate queries across tenants when `group is None`. Always pass `group=group` or use fail-closed scoping.

### 2.2 Role Matrix (`tracker.User.user_type`)
- **`PRIMARY`**: Full administrative access across all modules, investments, real estate, and MCP tools.
- **`ACCOUNT_HOLDER`** (Spouse/Partner): View-only savings dashboard, full HRA, Spends (with `Investments` category strictly masked), and Jewellery. Portfolio views return `403 Forbidden`.
- **`LANDLORD`**: Strictly view-only access restricted to the HRA rent records (`/hra/`). All other modules return `403 Forbidden`.

### 2.3 Vault Gate (`_vault_gate`)
- Sensitive views in `portfolio` and `jewellery` call `_vault_gate(request)` before execution.
- Gated behind a 30-minute session TTL with biometric (WebAuthn) or master password unlock.
- Brute-force rate limiting enforces 5 attempts / 5-minute lockout via Django's cache.

### 2.4 Strict Secrets Protection
- **NEVER** inspect, echo, grep, dump, or commit secret files:
  - `.env`, `scripts/DEPLOY.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, `**/google-service-account*.json`.
- NEVER run shell commands dumping environment variables (`env`, `printenv`, `echo $SECRET_KEY`).
- Reference variable names only and refer to `.env.example` or `scripts/DEPLOY.env.example`.

---

## 3. Financial Precision & Indian Fiscal Conventions

1. **Python `Decimal` Exclusively**:
   - ALWAYS use `decimal.Decimal` for currency amounts, holdings, weights, prices, and rates.
   - NEVER use `float` for monetary balances or aggregations.
   - For chart rendering contexts requiring JSON numbers, convert to float only at the terminal serialization layer.
   - Percentage calculations MUST use `pftracker.utils.pct(part, total)` or `pnl_pct(pnl, invested)` to guarantee 2-decimal quantization (`Decimal('0.01')`) and type safety.
2. **Indian Financial Year (April 1 – March 31)**:
   - Dates in January, February, or March belong to the previous calendar year's FY (e.g. February 2026 is FY 2025-26).
   - Use `fy_start_year(date)` and `fy_label(fy_start)` from `pftracker.utils`.
3. **Number Formatting**:
   - Use Indian numbering format (Lakhs `L`, Crores `Cr`, e.g., `₹12,50,000`) via `indian_comma` and `compact_inr` template tags.

---

## 4. Query Performance & Anti-N+1 Mandate

1. **Mandatory Relationship Prefetching**:
   - Any query whose results iterate over foreign keys or one-to-one relations MUST use `.select_related()` (e.g. `Transaction.objects.select_related('user', 'category')`).
   - Any query iterating over reverse foreign keys or many-to-many relationships MUST use `.prefetch_related()`.
   - Never query foreign keys inside loops or list comprehensions.
2. **Bulk Operations**:
   - Use `bulk_create` and `bulk_update` with `batch_size` for multi-record mutations.
   - Always specify `update_fields=[...]` when calling `.save()` on existing instances to prevent race conditions and unnecessary column writes.
3. **Thread-Safe Concurrency**:
   - When executing parallel operations (such as multi-stage DAG nodes), always use `DjangoSafeThreadPoolExecutor` or `safe_async_to_thread` from `pftracker.concurrency` to prevent database connection leaks and thread-local connection pollution.
4. **Caching**:
   - Use Django's cache framework (`from django.core.cache import cache`) for transient rate-limiting and expensive computations.

---

## 5. Python Typing, Docstrings & Module Contracts

- **Type Annotations**:
  - All new or refactored functions, methods, and classes must include Python 3.12+ type hints (`int | None`, `list[str]`, `Decimal`).
- **Docstrings**:
  - Provide concise, informative docstrings explaining parameters, return contracts, and tenant scoping.
- **Contract Integrity**:
  - Keep models in `models.py`, business operations in `services.py`, UI validation in `forms.py`, and endpoint routing in `views.py`.

---

## 6. Error Recovery & Fault Tolerance

1. **AI Pipeline Fallbacks**:
   - Every multi-stage AI workflow (`PortfolioInsightsDAG`, `run_land_appraisal_dag`) MUST implement deterministic, mathematically grounded fallbacks for every stage.
   - In the event of model provider outages, rate limits (HTTP 429), or service errors (HTTP 503), the pipeline must seamlessly fall back and complete without crashing.
2. **Safe Error Trapping**:
   - Trap expected exceptions (`ObjectDoesNotExist`, `ValueError`, `KeyError`, `requests.RequestException`) cleanly.
   - Avoid broad bare `except:` clauses. Log structured warnings with context.

---

## 7. Code Intelligence with CodeGraph

- The repository symbol knowledge graph is maintained in `.codegraph/`.
- Prefer querying CodeGraph tools (`codegraph_query`, `codegraph_node`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`, `codegraph_affected`) or CLI commands (`codegraph query`, `codegraph callers`, etc.) over blind ripgrep searches.
- Before refactoring shared utility or service functions, check the blast radius using `codegraph impact <symbol>`.
- Run `codegraph sync` after adding or restructuring modules.

---

## 8. Mandatory Pre-Push Verification & Git Standards

Before committing or pushing code, Antigravity agents MUST execute and verify:
1. **Lint Check**:
   ```bash
   ./venv/bin/ruff check --select F,E9 .
   ```
   Must pass with **0 errors**.
2. **Test Suite**:
   ```bash
   ./venv/bin/python manage.py test --keepdb
   ```
   Must pass **100%**.
3. **CodeGraph Sync**:
   ```bash
   codegraph sync
   ```
4. **Conventional Commits**:
   - Format: `<type>(<scope>): <summary>` (types: `feat`, `fix`, `perf`, `refactor`, `test`, `chore`, `docs`).
   - Scope must specify the affected module (e.g., `tracker`, `portfolio`, `expenses`, `jewellery`, `mcp`, `agents`).
   - Every commit message MUST include an explanatory body detailing motivation and a bulleted list of modified components. Never use vague one-liners.
