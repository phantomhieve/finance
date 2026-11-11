# Vault — Personal Finance Dashboard & Intelligence Hub

A household wealth management, multi-asset portfolio ledger, and automated expense intelligence platform purpose-built for the Indian financial ecosystem (April–March Financial Year, INR Lakh/Crore formatting, Gaj/Bigha land units, live 24K/22K Gold & Silver spot pricing, EPF, NPS, Zerodha Google Sheets sync, and automated Gmail bank/card alert & PDF statement reconciliation). Runs on a dual ASGI router serving both the Django web application and a FastMCP Server-Sent Events (`/mcp/sse`) endpoint for external AI clients.

---

## Features

- **Monthly Savings Tracker (`/`)** — Annual and monthly savings targets, mid-year salary step-ups (`GoalIncrement`), single-month adjustments (`MonthlyGoalAdjustment`), cumulative carry-forward pace tracking, and monthly commentary per Indian FY (April–March).
- **Automated Household Expense Intelligence (`/expenses/`)** — Automated household spend tracking and reconciliation:
  - **Multi-Inbox Gmail OAuth 2.0 Sync**: Connects household Gmail accounts (`gmail.readonly`) in parallel to ingest transaction alerts across 30+ Indian banks, credit cards, and UPI apps.
  - **Encrypted Credit Card Statement Reconciliation (`/expenses/statements/`)**: Unlocks password-protected PDF statements (`pypdf`), extracts line items, and executes a **3-Stage Reconciliation Pipeline** (Deterministic Rule Match → AI Candidate Disambiguation → Auto-Add & Refund Pairing) without double-counting email alerts.
  - **Dual-Leg Transfer & Bill Settlement**: Pairs bank account debits (`Leg 1`) against credit card bill credits (`Leg 2`) or statement payments (`settle_internal_movements` & `_collapse_transfer_legs`), excluding internal movements from spend totals and rendering a single unified `Bank → Card` ledger row.
  - **Credit Card EMI & Loan Tracker**: Detects active EMIs from statement narrations, tracks installment progress (`emi_installment_num / emi_total_installments`), separates Principal vs. Interest components, and propagates tenure metadata across billing cycles.
  - **Net Spend & Refund Accounting**: Nets partial/full refunds (`refunded_amount`, `refund_of` links, and standalone credit reversals) to report true household burn.
  - **Annual FY Spend Review & Subscription Matrix (`/expenses/year/`)**: Full April–March analytical matrix with Fixed vs. Discretionary split, YoY pace comparisons, category 12-month sparklines, a **12-Month Recurring Subscription Cadence Matrix**, and **AI Forensic Anomaly Auditing** (`ExpenseAuditRun`).
  - **Self-Learning Categorization & Control Center (`/expenses/settings/`)**: 4-tier categorization waterfall (`Household MerchantRule` → `Global BrandKnowledge / KeywordKnowledge` → `Channel Heuristics` → `AI Batch Categorizer`) with one-click retrospective re-filing.
- **HRA & Rent Tracker (`/hra/`)** — Tracks rent paid, landlord receipts, maintenance deductions, and balance reconciliations with dedicated landlord read-only views.
- **Multi-Asset Portfolio Tracker (`/portfolio/`)** — Consolidated household net-worth and 11-asset-class ledger:
  - **Equities & Mutual Funds**: Multi-account Zerodha holdings (Direct Stocks, Index Funds, Active MFs) synced from Google Sheets with consolidated blotter views.
  - **Fixed Income & Retirement**: EPF ledger (Employee + Employer + Interest), PPF (`pf`), NPS state tracking, and Fixed Deposits (`SIMPLE`, `MONTHLY`, `QUARTERLY`, `ANNUAL` compounding).
  - **Liquid Cash, Bonds & Crypto**: Bank/liquid positions, sovereign/corporate bonds, and crypto holdings.
  - **US Stocks & RSUs**: Dollar-denominated RSU vests with live USD/INR conversion.
  - **Real Estate Holdings**: Supports North Indian land units (`Gaj`, `Sq. Yards`, `Sq. Ft`, `Bigha`, `Acres`, `Sq. Meters`), stamp duty cost basis, rental yields, holding CAGR, annual April 1 AI land revaluation (`portfolio/land_appraisal.py`), audit trail remarks, and HTML valuation certificates.
  - **Child Portfolio Segregation (`is_baby`)**: Ring-fences assets earmarked for a child's future (`/portfolio/baby/`) from the Master Portfolio.
- **Jewellery Vault (`/jewellery/`)** — Physical precious metals & ornament catalog (Gold, Silver, Platinum, Diamond) with purity fineness multipliers (`24K`, `22K`, `18K`, `14K`, `999`, `925`), custody tracking (`Bank Locker` vs. `Home Safe`), live bullion spot valuations, UUID-isolated photo storage, HEIC/HEIF conversion, and cached WebP thumbnails.
- **Quant-Grounded Portfolio AI DAG (`portfolio/dag.py`)** — Pre-computes exact `Decimal` concentration, liquidity, crash-drawdown, hurdle-rate, and tax-harvesting metrics in Stage 0 before running parallel Flash diagnostic lenses (`gemini-3.8-flash`), Carbon tax & editorial synthesis (`gemini-4-carbon`), and a deterministic composite health score reducer:
  $$\text{Health Score} = \text{round}(0.30 \times S_{\text{allocation}} + 0.25 \times S_{\text{quality}} + 0.25 \times S_{\text{strategy}} + 0.20 \times S_{\text{macro}})$$
- **Fiduciary Land Appraisal DAG (`portfolio/land_appraisal.py`)** — 3-stage annual valuation pipeline (`gemini-4-carbon` with Google Search grounding + deterministic `Decimal` fiduciary haircuts: `30%` Speculative Ask Haircut, Dynamic Illiquidity & Friction Discount `max(15%, 9% + 0.75 * Repo)`, Execution Slippage Penalty, and `Repo + CPI + 3%` Macro YoY Ceiling) that separates approved carrying value from unrealized speculative buffer (`templates/emails/land_appraisal.html`).
- **Unified AI Gateway (`pftracker/ai_gateway/`)** — Declarative `TaskProfile` router supporting Google Gemini (`gemini-4-carbon`, `gemini-3.8-flash`, `gemini-2.5-flash-lite`) and OpenAI-compatible Shakti Cloud (`deepseek-r1`, `llama3_3`) with Dev/Prod model & thinking tiering, multi-key HTTP 429 rotation, cross-provider cascade failover, Indian financial PII scrubbing, nonced XML prompt-injection boundaries, and log secret redaction. See [`docs/ux/0001-ai-calling-and-dag-strategy.md`](docs/ux/0001-ai-calling-and-dag-strategy.md).
- **Model Context Protocol (MCP) Server (`/mcp/sse`)** — Native FastMCP SSE endpoint exposing 30+ read/write financial tools to AI assistants (Claude, ChatGPT, Cursor) secured by OAuth 2.0 PKCE (`RFC 9700` BCP hardening), `PRIMARY` role & scope enforcement (`OAuthBearerMiddleware`), and reversible `MCPAuditLog` snapshots.

---

## User Roles, Multi-Tenancy & Security Architecture

Every household is isolated to an `AccountGroup` with per-household feature flags (`HouseholdConfig`) and fail-closed query scoping (`_gf(group)`):

| Capability / Module | Primary Account Holder (`PRIMARY`) | Account Holder (`ACCOUNT_HOLDER`) | Landlord (`LANDLORD`) |
| :--- | :--- | :--- | :--- |
| **Savings Dashboard (`/`)** | Full CRUD | View Only (Household Primary's ledger) | Redirected to `/hra/` |
| **HRA & Rent (`/hra/`)** | Full CRUD | Full CRUD | View Only (Rent ledger) |
| **Portfolio Tracker (`/portfolio/`)** | Full Access (behind `_vault_gate`) | No Access | No Access |
| **Jewellery Vault (`/jewellery/`)** | Full Access (behind `_vault_gate`) | View Only — valuations & CRUD hidden (behind `_vault_gate`) | No Access |
| **Expense Tracker (`/expenses/`)** | Full Access (all categories) | Full Access (**`Investments` category masked**) | No Access |
| **Personal Notes (`/notes/`)** | Full CRUD (user-scoped) | Full CRUD (user-scoped) | No Access |
| **MCP Server (`/mcp/sse`)** | Allowed (`read` / `write` OAuth scopes) | Blocked (`403 Forbidden`) | Blocked (`403 Forbidden`) |
| **Django Admin (`/vault-manage/`)** | Superuser Only | No Access | No Access |

### Defense-in-Depth Controls
- **Vault Gate & WebAuthn Passkeys**: Portfolio and Jewellery require secondary household password or WebAuthn biometric unlock (`30-minute` TTL via `_vault_gate`), and Expenses enforces a `4-hour` unlock session (`EXPENSES_UNLOCK_TTL_SECONDS`) when a household vault password is set. Unlock endpoints enforce cache-backed brute-force lockouts (`5` attempts / `5` minutes) and single-use WebAuthn challenges.
- **Investment Privacy Masking (`_hides_investments`)**: Non-portfolio household members (`ACCOUNT_HOLDER`) share household expenses and Gmail sync while all transactions, totals, and rules in the `Investments` category remain masked.
- **Encryption at Rest (`expenses/crypto.py`)**: Gmail OAuth refresh tokens (`GmailAccount.refresh_token_enc`; short-lived access tokens remain in-memory on `GmailClient`), credit card PDF binaries (`CardStatement.pdf_blob`), statement unlock passwords (`PaymentSource.statement_password_enc`), and household Google Sheets service account JSONs (`HouseholdConfig.google_credentials_json`) are encrypted at rest with Fernet (`EXPENSES_ENCRYPTION_KEY`, falling back to `SHA-256('vault-expenses:' + SECRET_KEY)` when unset).
- **Transport, CSP & Mutation Hardening (`pftracker/settings.py`)**: Enforces `ContentSecurityPolicyMiddleware` (`SECURE_CSP`), `X_FRAME_OPTIONS = 'DENY'`, `HttpOnly` / `SameSite=Lax` cookies, HSTS in production, fail-closed `DJANGO_SECRET_KEY` check when `DEBUG=False`, and `@require_POST` + CSRF tokens on all mutations.

---

## Expense Intelligence Pipeline

```text
 ┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
 │   Gmail OAuth Inboxes   │      │  Encrypted Card PDFs    │      │   Manual / MCP Entry    │
 │ (30+ Indian Bank Alerts)│      │ (Password Unlock/pypdf) │      │ (Quick Add / AI Agent)  │
 └────────────┬────────────┘      └────────────┬────────────┘      └────────────┬────────────┘
              │                                │                                │
              ▼                                ▼                                ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────┐
 │                     Ingestion & Normalization (`expenses/ingestion.py`)                   │
 │  • Merchant normalization & sensitive data masking (`mask_sensitive`)                     │
 │  • Auto-detection of PaymentSource (Bank, Credit Card, UPI, Wallet) + Deduplication key   │
 └─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                               │
              ┌────────────────────────────────┼────────────────────────────────┐
              ▼                                ▼                                ▼
 ┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
 │  4-Tier Categorization  │      │ 3-Stage PDF Reconciler  │      │  Dual-Leg Settlement    │
 │ 1. User MerchantRule    │      │ 1. Rule Match (±3d, ₹1) │      │ • Pairs Bank Debit Leg1 │
 │ 2. Brand/Keyword DB     │      │ 2. AI Candidate Match   │      │   & Card Credit Leg2    │
 │ 3. Channel Heuristics   │      │ 3. Auto-Add + Refunds   │      │ • Excludes from Spend   │
 │ 4. AI Batch Categorizer │      │ • EMI Tenure Extraction │      │ • Collapses Feed Rows   │
 └─────────────────────────┘      └─────────────────────────┘      └─────────────────────────┘
```

---

## AI Portfolio DAG & Gateway Architecture

Full specification: [`docs/ux/0001-ai-calling-and-dag-strategy.md`](docs/ux/0001-ai-calling-and-dag-strategy.md).

```text
                        ┌────────────────────────────────────────────────────────┐
                        │  Stage 0: Python Decimal Quant Engine (<5ms, 0 tokens) │
                        │  • HHI, full-universe tail losers, Tier 1/2/3 liquidity│
                        │  • -35% crash INR, FD vs 8.15% EPF hurdle, Sec 112A    │
                        └──────────────────────────┬─────────────────────────────┘
                                                   │ (Surgical Slices + Quant Metrics)
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
     ┌─────────────────────────────┐┌─────────────────────────────┐┌─────────────────────────────┐
     │  Stage 1A: Allocation Lens  ││   Stage 1B: Asset Quality   ││    Stage 1C: Macro Stress   │
     │  gemini-3.8-flash (budget=0)││  gemini-3.8-flash (budget=0)││  gemini-3.8-flash (budget=0)│
     └──────────────┬──────────────┘└──────────────┬──────────────┘└──────────────┬──────────────┘
                    │                              │                              │
                    └──────────────────────────────┼──────────────────────────────┘
                                                   ▼ (Fan-in)
                                    ┌─────────────────────────────┐
                                    │ Stage 2: Strategy Synthesis │
                                    │ gemini-4-carbon (HIGH)      │
                                    └──────────────┬──────────────┘
                                                   ▼
                                    ┌─────────────────────────────┐
                                    │ Stage 3: Editorial & Critic │
                                    │ gemini-4-carbon (HIGH) +    │
                                    │ Deterministic Score Reducer │
                                    └─────────────────────────────┘
```

- **Database & Concurrency Architecture**:
  - **Connection Pooling (`pftracker/settings.py`)**: `CONN_MAX_AGE=600` in production (`0` in dev/tests) with `CONN_HEALTH_CHECKS=True` and PostgreSQL TCP keepalives.
  - **SQLite WAL PRAGMAs (`pftracker/db_optimizations.py`)**: Configures `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=15000`, and `cache_size=-64000` (`64MB` page cache) on connection creation.
  - **Leak-Free Worker Pools (`pftracker/concurrency.py`, `pftracker/asgi.py`)**: `DjangoSafeThreadPoolExecutor` cleans up thread-bound Django connections around parallel DAG stages, Gmail sync workers, and PDF chunk extractors; `DatabaseConnectionLifecycleMiddleware` guards `/mcp` ASGI routes.

---

## Tech Stack

- **Backend**: Python 3.12+, Django 6.0, Starlette (ASGI router), FastMCP, `django-unfold` (`/vault-manage/` admin)
- **Application Server**: Gunicorn with `uvicorn.workers.UvicornWorker`
- **Database**: PostgreSQL (production via `dj-database-url`) / SQLite WAL (local development)
- **Frontend & Design System**: Tailwind CSS v4 (`@tailwindcss/browser@4`), DaisyUI v5 (`night` dark folio default / `winter` archival light theme), authored Private Bank Folio tokens & components (`static/css/style.css`, [`DESIGN.md`](DESIGN.md)), Chart.js 4, Inter font, Material Symbols Outlined
- **AI & Code Intelligence**: Unified AI Gateway (`google-genai` SDK + OpenAI-compatible Shakti Cloud), Pydantic structured schemas, CodeGraph MCP
- **Authentication & Security**: `django-allauth` (Google SSO), `py_webauthn` (WebAuthn passkeys), `django-oauth-toolkit` (OAuth 2.0 PKCE for MCP), `cryptography` (Fernet encryption at rest)
- **Data & Media**: `gspread` (Google Sheets sync), `pypdf` (encrypted statement parsing), `Pillow` + `pillow-heif` (HEIC/WebP conversion)

---

## Local Development Setup

### 1. Virtual Environment & Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment & Seed Data
```bash
cp .env.example .env
python manage.py migrate
python seed_data.py
```

### 3. Run Development Server
```bash
python manage.py runserver 8000
```

Open `http://127.0.0.1:8000/`. When `DJANGO_DEBUG=True`, use the **Dev Mode** switcher on `/login/` to sign in as:
- **`atul`** (`PRIMARY` — Full household, portfolio, jewellery, and expense access)
- **`spouse`** (`ACCOUNT_HOLDER` — Shared savings view, HRA, read-only jewellery catalog, and expenses with `Investments` masked)
- **`landlord`** (`LANDLORD` — Read-only HRA rent verification view)

---

## Testing, Linting & Pre-Push Verification

Run the local verification suite before committing or pushing (enforced in `.github/workflows/ci.yml`):

```bash
# 1. Ruff pyflakes & syntax check (0 errors)
./venv/bin/ruff check --select F,E9 .

# 2. Django system & migration checks
./venv/bin/python manage.py check --fail-level WARNING
./venv/bin/python manage.py makemigrations --check --dry-run

# 3. Full multi-app test suite
./venv/bin/python manage.py test --keepdb

# 4. Sync CodeGraph AST index after structural edits
codegraph sync
```

---

## Management Commands

| Command | App | Description |
| :--- | :--- | :--- |
| `sync_expenses [--email X] [--days N]` | `expenses` | Syncs bank/card alerts & PDF statements from Gmail, runs categorization, and settles internal transfers |
| `ai_categorize_day` | `expenses` | Categorizes yesterday's uncategorized expenses via the AI Gateway |
| `backfill_statements [--since YYYY-MM]` | `expenses` | Backfills historical credit card PDF statements from Gmail with 3-stage reconciliation |
| `expense_reminders` | `expenses` | Dispatches credit card bill due-date reminder emails (5-day, 1-day, and due-day alerts) |
| `send_expense_summary` | `expenses` | Generates and emails the monthly household spend & category report |
| `seed_expenses_dev` | `expenses` | Populates sample expense data for local development |
| `sync_sheets` | `portfolio` | Syncs Zerodha equity and mutual fund holdings from Google Sheets |
| `refresh_prices` | `portfolio` | Fetches latest 24K Gold, Silver, and USD/INR rates and updates `CommodityPrice` |
| `take_snapshot` | `portfolio` | Captures month-end `MonthlySnapshot` of net worth, capital added, and market returns |
| `generate_insights` | `portfolio` | Executes the Portfolio AI DAG (`portfolio/dag.py`) and persists `PortfolioInsight` |
| `appreciate_land` | `portfolio` | Executes the April 1 3-stage AI land appraisal DAG (`portfolio/land_appraisal.py`) and emails valuation certificate |
| `send_weekly_brief` | `portfolio` | Generates and emails the Sunday AI Equity Intelligence Brief |
| `send_monthly_summary` | `portfolio` | Dispatches the monthly AI portfolio health & performance email |
| `send_fy_review` | `portfolio` | Generates the April 1 Financial Year close wealth review |
| `test_shakti_ai` | `portfolio` | Verifies AI Gateway connectivity, key rotation, and DAG latency |
| `backup_db --bucket NAME` | `portfolio` | Dumps PostgreSQL database, compresses archive, and uploads to Google Cloud Storage |
| `generate_jewellery_thumbnails` | `jewellery` | Generates cached WebP thumbnails for uploaded ornament photos |
| `run_mcp_server` | `mcp_server` | Launches the FastMCP server in `stdio` transport mode for local IDE/CLI agents |

---

## Scheduled Tasks (`deploy/cron`)

Production cron schedule (`CRON_TZ=Asia/Kolkata`):

| Schedule | Command | Purpose |
| :--- | :--- | :--- |
| **Hourly at `:17`** | `sync_expenses` | Ingest Gmail bank, UPI, and credit card alert emails |
| **Daily `02:00 IST`** | `ai_categorize_day` | Batch-categorize yesterday's uncategorized expenses |
| **Daily `06:00 IST`** | `sync_sheets ; refresh_prices` | Sync Zerodha Google Sheets & refresh Gold/Silver spot rates |
| **Daily `09:00 IST`** | `expense_reminders` | Send credit card statement due-date reminders |
| **Sunday `06:30 IST`** | `send_weekly_brief` | Weekly AI Equity Intelligence Brief email |
| **1st of Month `06:00 IST`** | `take_snapshot` | Monthly portfolio net-worth snapshot |
| **1st of Month `06:30 IST`** | `send_monthly_summary` | Monthly AI portfolio review email |
| **1st of Month `08:00 IST`** | `sync_expenses ; send_expense_summary` | Final inbox sync + monthly household spend report |
| **1st of April `05:45 IST`** | `appreciate_land` | Annual FY-end AI land revaluation & certificate email |
| **1st of April `06:45 IST`** | `send_fy_review` | Financial Year close annual wealth report |

Database backups run via `scripts/backup-all-dbs.sh` / `manage.py backup_db`.

---

## Project Structure

```text
finance/
├── pftracker/               # Project settings, OAuth discovery, concurrency & ASGI router
│   ├── ai_gateway/          # Unified AI Gateway (TaskProfile config, router, circuit breaker, sanitizer)
│   ├── asgi.py              # Dual ASGI router (/mcp FastMCP + Django HTTP)
│   ├── concurrency.py       # DjangoSafeThreadPoolExecutor & safe async/thread DB workers
│   ├── context_processors.py# Global household_config & role template context
│   ├── db_optimizations.py  # SQLite WAL & concurrency PRAGMA signal hooks
│   ├── settings.py          # Django 6.0, Unfold admin, CSP, OAuth2 PKCE & AI settings
│   ├── urls.py              # Root URL routing, .well-known OAuth metadata & /vault-manage/
│   └── utils.py             # Indian FY helpers (fy_start_year, fy_label) & Decimal pct helpers
├── tracker/                 # Multi-tenancy, Monthly Savings, Goals, HRA & Notes
│   ├── models.py            # AccountGroup, User, HouseholdConfig, WebAuthnCredential, Transaction, HRAExpense, Note
│   ├── services.py          # Savings & goal pacing calculations
│   └── views.py             # Savings dashboard, HRA ledger, Notes CRUD, SSO & dev-login
├── portfolio/               # Multi-Asset Wealth Ledger & AI Valuation DAGs
│   ├── ai/                  # Portfolio AI schemas, prompt builders & gateway runners
│   ├── templatetags/        # indian_format.py (inr, inr_short, indian_number filters)
│   ├── dag.py               # Stage 0 Decimal quant + 3-stage parallel/sequential Portfolio DAG
│   ├── land_appraisal.py    # 3-stage search-grounded fiduciary land revaluation DAG
│   ├── models.py            # Holdings across 11 asset classes, FinancialGoal, MonthlySnapshot, PortfolioInsight
│   ├── services.py          # Portfolio summaries, Google Sheets sync, bullion/FX rates & goal roadmaps
│   └── views.py             # Master & Child (is_baby) views, asset detail views, WebAuthn & _vault_gate
├── expenses/                # Automated Household Expense Intelligence
│   ├── ai/                  # Categorization, receipt/statement extraction, matching & anomaly prompts/runners
│   ├── analytics.py         # Net spend math, month_summary, fy_summary, subscription_summary
│   ├── anomaly.py           # Forensic FY spend anomaly engine
│   ├── categories.py        # 4-tier categorization waterfall & retrospective learning
│   ├── crypto.py            # Fernet encryption at rest (EXPENSES_ENCRYPTION_KEY)
│   ├── emi.py               # Credit card EMI narration detection & tenure propagation
│   ├── gmail.py             # Gmail OAuth 2.0 client & thread-safe token refresh
│   ├── ingestion.py         # Merchant normalization, PaymentSource resolution & dual-leg settlement
│   ├── models.py            # Expense, ExpenseCategory, PaymentSource, GmailAccount, CardStatement, StatementLine
│   ├── parsing.py           # Parsers for 30+ Indian banks, credit cards & UPI alerts
│   ├── services.py          # Domain service facade
│   ├── statements.py        # Encrypted PDF reader & 3-stage statement reconciler
│   ├── sync.py              # Parallel multi-inbox Gmail synchronization
│   └── views.py             # Monthly workbench, FY matrix, Statement reconciler & Settings control center
├── jewellery/               # Physical Precious Metals & Ornament Vault
│   ├── models.py            # JewelleryItem, purity fineness factors & media cleanup
│   ├── utils.py             # HEIC/HEIF conversion & cached WebP thumbnail generator
│   └── views.py             # Custody ledger, assay detail & authenticated photo streaming
├── mcp_server/              # Model Context Protocol (MCP) Server
│   ├── audit.py             # Reversible before/after JSON snapshot logging
│   ├── middleware.py        # OAuthBearerMiddleware (OAuth 2.0 PKCE, PRIMARY role & scope guard)
│   ├── oauth.py             # UserBoundGrantValidator & DCR permission guards
│   └── server.py            # 30+ FastMCP read/write financial tools
├── docs/                    # Architecture & UX specifications
│   ├── adr/                 # ADR-0001 Unified AI Gateway & Quant-Grounded DAG spec
│   └── ux/                  # Page-level Information Architecture (IA.md) & component patterns (components.md)
├── templates/               # Private Bank Folio templates (tracker, portfolio, expenses, jewellery, public, unfold)
└── static/                  # Design system CSS (style.css, public.css, admin_theme.css) & modular JS
```
