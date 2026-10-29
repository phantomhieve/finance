# Vault — Personal Finance Dashboard & Intelligence Hub

A production-grade personal finance, multi-asset wealth management, and household expense intelligence platform purpose-built for the Indian financial ecosystem (April–March Financial Year, INR Lakh/Crore formatting, Gaj/Bigha land units, live 24K/22K Gold & Silver spot pricing, EPF, NPS, Zerodha Google Sheets sync, and automated Gmail bank/card alert & PDF statement reconciliation). Features a dual ASGI architecture serving both the Django web application and a FastMCP Server-Sent Events (`/mcp/sse`) endpoint for autonomous AI agents.

---

## Features

- **Monthly Savings Tracker (`/`)** — Set annual and monthly savings targets, salary hike step-ups (`GoalIncrement`), single-month adjustments (`MonthlyGoalAdjustment`), cumulative carry-forward pace tracking, and monthly performance commentary per Indian FY (April–March).
- **Automated Household Expense Intelligence (`/expenses/`)** — End-to-end household spend tracking without manual bookkeeping:
  - **Multi-Inbox Gmail OAuth 2.0 Sync**: Connects partner Gmail accounts (`gmail.readonly`) to automatically ingest transaction alerts across 30+ Indian banks, credit cards, and UPI apps.
  - **Encrypted Credit Card Statement Reconciliation (`/expenses/statements/`)**: Decrypts password-protected PDF statements (`pypdf`), extracts line items, and executes a **3-Stage Reconciliation Pipeline** (Deterministic Rule Match → AI Candidate Disambiguation → Auto-Add & Refund Pairing) so statement backfills never double-count email alerts.
  - **Dual-Leg Transfer & Bill Settlement**: Automatically pairs bank account debits (`Leg 1`) against credit card bill credits (`Leg 2`) or statement payments (`settle_internal_movements` & `_collapse_transfer_legs`), excluding internal movements from spend totals and collapsing redundant transfer legs into a single unified `Bank → Card` feed row.
  - **Credit Card EMI & Loan Tracker**: Detects active EMIs from statement narrations, tracks installment progress (`emi_installment_num / emi_total_installments`), separates Principal vs. Interest components, and propagates tenure metadata across statement cycles.
  - **Net Spend & Refund Accounting**: Tracks partial/full refunds (`refunded_amount`, `refund_of` links, and standalone credit reversals) to report true net household burn.
  - **Annual FY Spend Review & Subscription Matrix (`/expenses/year/`)**: Full April–March analytical breakdown featuring Fixed vs. Discretionary split, YoY pace comparisons, category 12-month sparklines, a **12-Month Recurring Subscription Cadence Matrix** (detecting active/paused/irregular bills and annualized run-rate), and **AI Forensic Anomaly Auditing** (`ExpenseAuditRun`).
  - **Self-Learning Categorization & Control Center (`/expenses/settings/`)**: 4-tier categorization waterfall (`Household MerchantRule` → `Global BrandKnowledge / KeywordKnowledge` → `Channel Heuristics` → `AI Batch Categorizer`) with one-click retrospective re-filing across historical transactions.
- **HRA & Rent Tracker (`/hra/`)** — Track rent paid, landlord receipts, maintenance deductions, and revert balance reconciliations with dedicated landlord read-only views.
- **Multi-Asset Portfolio Tracker (`/portfolio/`)** — Consolidated household net-worth and asset management:
  - **Equities & Mutual Funds**: Multi-account Zerodha holdings (Direct Stocks, Index Funds, Active MFs) synced from Google Sheets with consolidated cross-account views.
  - **Fixed Income & Retirement**: EPF ledger (Employee + Employer + Interest), NPS state tracking, and Fixed Deposits (`SIMPLE`, `MONTHLY`, `QUARTERLY`, `ANNUAL` compounding math).
  - **Liquid Cash, Bonds & Crypto**: Cash positions, sovereign/corporate bonds, and crypto holdings.
  - **US Stocks & RSUs**: Dollar-denominated RSU vests (e.g., Uber) with live USD/INR currency conversion.
  - **Real Estate Holdings**: Supports North Indian land units (`Gaj`, `Sq. Yards`, `Sq. Ft`, `Bigha`, `Acres`, `Sq. Meters`), stamp duty cost basis, rental yields, holding CAGR, annual FY land appreciation, and 1-click micro-market LLM research prompts.
  - **Child Portfolio Segregation (`is_baby`)**: Isolate assets ear-marked for a child's future (`/portfolio/baby/`) from the Master Portfolio with instant CSRF-protected toggle controls.
- **Jewellery Vault (`/jewellery/`)** — Physical precious metals & ornament catalog (Gold, Silver, Platinum, Diamond) with purity fineness multipliers (`24K`, `22K`, `18K`, `14K`, `999`, `925`), storage location tracking (`Bank Locker` vs. `Home Safe`), live spot-rate valuations, UUID-isolated photo storage, iPhone HEIC/HEIF conversion, and cached WebP thumbnails.
- **AI Portfolio Insights & Multi-Stage DAG Engine** — Directed Acyclic Graph workflow (`portfolio/dag.py`) running parallel diagnostic lenses (Allocation & Liquidity, Asset Quality & Legacy MF Audit, Macro Regime & `-35%` Crash Stress), Indian FY tax harvesting synthesis (Section 112A LTCG & Section 54/54EC), and deterministic composite health scoring:
  $$\text{Health Score} = \text{round}(0.30 \times S_{\text{allocation}} + 0.25 \times S_{\text{quality}} + 0.25 \times S_{\text{strategy}} + 0.20 \times S_{\text{macro}})$$
- **Unified AI Gateway (`pftracker/ai_gateway/`)** — Centralized multi-provider routing engine supporting Shakti Cloud (`deepseek-r1`, `llama3_3`) and Google Gemini, featuring task-tier routing (`FAST`, `REASONING`, `RESEARCH`, `EXTRACTION`), multi-key pool rotation on HTTP 429 rate limits, circuit breakers, and automatic `DEBUG` vs. Production model tiering.
- **Model Context Protocol (MCP) Server (`/mcp/sse`)** — Native FastMCP SSE endpoint exposing 30+ read/write financial tools to external AI agents (Claude, ChatGPT, Cursor) secured by OAuth 2.0 PKCE, role/scope enforcement (`MCPTokenAuthMiddleware`), and reversible `MCPAuditLog` before/after snapshots.

---

## User Roles, Multi-Tenancy & Security Architecture

Vault isolates every household to an `AccountGroup` with per-household feature flags (`HouseholdConfig`) and fail-closed query scoping (`_gf(group)`):

| Capability / Module | Primary Account Holder (`PRIMARY`) | Account Holder (`ACCOUNT_HOLDER`) | Landlord (`LANDLORD`) |
| :--- | :--- | :--- | :--- |
| **Savings Dashboard (`/`)** | Full CRUD | View Only (Household Primary's data) | Redirected to `/hra/` |
| **HRA & Rent (`/hra/`)** | Full CRUD | Full CRUD | View Only (Rent ledger) |
| **Portfolio Tracker (`/portfolio/`)** | Full Access (behind `_vault_gate`) | No Access | No Access |
| **Jewellery Vault (`/jewellery/`)** | Full Access (behind `_vault_gate`) | Full Access (behind `_vault_gate`) | No Access |
| **Expense Tracker (`/expenses/`)** | Full Access (all categories) | Full Access (**`Investments` category masked**) | No Access |
| **Personal Notes (`/notes/`)** | Full CRUD (user-scoped) | Full CRUD (user-scoped) | No Access |
| **MCP Server (`/mcp/sse`)** | Allowed (`read` / `write` OAuth scopes) | Blocked (`403 Forbidden`) | Blocked (`403 Forbidden`) |
| **Django Admin (`/vault-manage/`)** | Superuser Only | No Access | No Access |

### Defense-in-Depth Security Controls
- **Vault Gate (`_vault_gate`) & WebAuthn Biometrics**: Portfolio and Jewellery routes require secondary authentication via household password or WebAuthn passkeys (Face ID / Touch ID) with a 30-minute rolling session TTL, single-use challenge consumption, and cache-backed brute-force lockout (5 attempts / 5 minutes).
- **Investment Privacy Masking (`_hides_investments`)**: Non-portfolio household members (`ACCOUNT_HOLDER`) share household expenses and Gmail sync but are strictly prevented from viewing, filtering, or re-filing transactions or rules under the `Investments` category.
- **Encryption at Rest (`expenses/crypto.py`)**: Gmail OAuth refresh/access tokens, credit card PDF statement binaries, PDF unlock passwords, and per-household Google Sheets service account JSONs are encrypted at rest using Fernet (`VAULT_FERNET_KEY`).
- **Strict CSRF & POST-Only Mutations**: All state-changing actions across the platform enforce `@require_POST` and CSRF verification.

---

## Expense Intelligence Pipeline

```
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

## AI Portfolio DAG Architecture

Vault's portfolio intelligence (`portfolio/dag.py`) replaces monolithic prompts with a 3-stage fan-out / fan-in workflow routed through `pftracker/ai_gateway/`:

```
                        ┌────────────────────────────────────────────────────────┐
                        │          Raw Portfolio JSON + Live Macro Data          │
                        └──────────────────────────┬─────────────────────────────┘
                                                   │ (Anti-Token Dilution Slicing)
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
     ┌─────────────────────────────┐┌─────────────────────────────┐┌─────────────────────────────┐
     │  Stage 1A: Allocation Lens  ││   Stage 1B: Asset Quality   ││    Stage 1C: Macro Stress   │
     │  • SEBI Age Glide Path      ││  • Legacy MF Merge/Exit     ││  • Nifty PE Valuation Zone  │
     │  • HHI & Stock Conc. (>5%)  ││  • RE Micro-Market & Yield  ││  • -35% Equity Crash Drawdown│
     │  • Tier 1 Emergency Floor   ││  • EPF Hurdle Rate vs FD    ││  • Net Worth Momentum Trend │
     └──────────────┬──────────────┘└──────────────┬──────────────┘└──────────────┬──────────────┘
                    │                              │                              │
                    └──────────────────────────────┼──────────────────────────────┘
                                                   ▼ (Fan-in)
                                    ┌─────────────────────────────┐
                                    │ Stage 2: Strategy Synthesis │
                                    │ • Sec 112A LTCG Harvesting  │
                                    │ • Sec 54/54EC RE Indexation │
                                    │ • Goal Gap SIP Rebalancing  │
                                    └──────────────┬──────────────┘
                                                   ▼
                                    ┌─────────────────────────────┐
                                    │ Stage 3: Terminal Grounding │
                                    │ • Deterministic Health Score│
                                    │ • Deduplicated Insights     │
                                    │ • Executive Summary & Outlook│
                                    └─────────────────────────────┘
```

---

## Tech Stack

- **Backend**: Python 3.12+, Django 6.0, Starlette (ASGI router), FastMCP
- **Application Server**: Gunicorn with `uvicorn.workers.UvicornWorker`
- **Database**: PostgreSQL (production via `dj-database-url`) / SQLite (local development)
- **Frontend & Design System**: Tailwind CSS v4 (`@tailwindcss/cli`), DaisyUI v5 (`light` / `dark` themes), mobile-first Bento layouts with segmented tab switchers, Chart.js 4.4, Inter + JetBrains Mono fonts, Material Symbols Outlined
- **AI & Code Intelligence**: Unified AI Gateway (Shakti Cloud OpenAI-compatible API + Google GenAI SDK `google-genai`), Pydantic structured outputs, CodeGraph MCP (`@colbymchenry/codegraph`)
- **Authentication & Security**: Django AllAuth (Google SSO), `py_webauthn` (WebAuthn 2.0 passkeys), `django-oauth-toolkit` (OAuth 2.0 PKCE for MCP), `cryptography` (Fernet encryption at rest)
- **Data & Document Processing**: `gspread` (Google Sheets sync), `pypdf` (encrypted statement parsing), `Pillow` + `pillow-heif` (HEIC/WebP image processing)

---

## Local Development Setup

### 1. Prerequisites
Ensure Python 3.12+ and Node.js 20+ are installed:
```bash
python3 --version
node -v
```

### 2. Virtual Environment & Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
npm install
```

### 3. Environment & Database Configuration
```bash
cp .env.example .env
python manage.py migrate
python seed_data.py
```

### 4. Build Tailwind CSS & Run Server
```bash
npm run build:css
python manage.py runserver 8000
```

Open `http://127.0.0.1:8000/`. When `DJANGO_DEBUG=True`, use the **Dev Mode** login switcher on `/login/` to sign in as:
- **`atul`** (`PRIMARY` — Full household, portfolio, jewellery, and expense access)
- **`spouse`** (`ACCOUNT_HOLDER` — Shared savings view, HRA, jewellery, and expenses with investments masked)
- **`landlord`** (`LANDLORD` — Read-only HRA rent verification view)

---

## Testing, Linting & Pre-Push Verification

Before committing or pushing code, always run the local verification suite (enforced in GitHub Actions CI):

```bash
# 1. Rebuild compiled Tailwind v4 + DaisyUI 5 stylesheet (if templates/CSS changed)
npm run build:css

# 2. Run Ruff syntax & undefined-name linter (must pass with 0 errors)
./venv/bin/ruff check --select F,E9 .

# 3. Run the full Django test suite (167+ tests across all apps)
./venv/bin/python manage.py test expenses portfolio tracker jewellery mcp_server --keepdb

# 4. Sync the CodeGraph AST index (if symbols/files were added or moved)
codegraph sync
```

---

## Management Commands

| Command | App | Description |
| :--- | :--- | :--- |
| `sync_expenses [--email X] [--days N]` | `expenses` | Fetches new bank/card alerts & PDF statements from connected Gmail accounts, runs AI categorization, and settles internal transfers |
| `backfill_statements [--since YYYY-MM]` | `expenses` | Backfills historical credit card PDF statements from Gmail with deduplication and 3-stage reconciliation |
| `expense_reminders` | `expenses` | Dispatches credit card bill due-date reminder emails (5-day, 1-day, and due-day alerts) |
| `send_expense_summary` | `expenses` | Generates and emails the monthly household spend & category report |
| `sync_sheets` | `portfolio` | Syncs Zerodha equity and mutual fund holdings from Google Sheets |
| `refresh_prices` | `portfolio` | Scrapes latest 24K Gold and Silver spot rates (`goodreturns.in`) and updates `CommodityPrice` |
| `take_snapshot` | `portfolio` | Captures month-end `MonthlySnapshot` of net worth, capital added, and returns |
| `appreciate_land` | `portfolio` | Applies annual FY-end capital appreciation (+6%) to qualifying `RealEstateHolding` plots |
| `send_weekly_brief` | `portfolio` | Generates and emails the Sunday AI Equity Intelligence Brief |
| `send_monthly_summary` | `portfolio` | Dispatches the monthly AI portfolio health & performance email |
| `send_fy_review` | `portfolio` | Generates the annual April 1 Financial Year close wealth review |
| `test_shakti_ai` | `portfolio` | Tests AI Gateway connectivity, key rotation, and DAG execution latency |
| `backup_db --bucket NAME` | `tracker` | Dumps PostgreSQL database, compresses archive, and uploads to Google Cloud Storage |
| `run_mcp_server` | `mcp_server` | Launches the FastMCP server in `stdio` transport mode for local IDE/CLI agents |

---

## Scheduled Tasks (Production Cron)

Recommended production schedule (`CRON_TZ=Asia/Kolkata`):

| Schedule | Command | Purpose |
| :--- | :--- | :--- |
| **Hourly at `:17`** | `sync_expenses` | Ingest Gmail bank, UPI, and credit card alert emails |
| **Daily `06:00 IST`** | `sync_sheets && refresh_prices` | Sync Zerodha holdings & refresh Gold/Silver spot rates |
| **Daily `09:00 IST`** | `expense_reminders` | Credit card statement due-date reminders |
| **Daily `23:30 IST`** | `backup_db` | Automated PostgreSQL encrypted backup to GCS |
| **Sunday `06:30 IST`** | `send_weekly_brief` | Weekly AI Equity Intelligence Brief email |
| **1st of Month `05:45 IST`** | `appreciate_land` | Annual April 1 land valuation step-up |
| **1st of Month `06:00 IST`** | `take_snapshot` | Monthly portfolio net-worth snapshot |
| **1st of Month `06:30 IST`** | `send_monthly_summary` | Monthly AI portfolio review email |
| **1st of Month `08:00 IST`** | `sync_expenses && send_expense_summary` | Monthly household expense report |
| **1st of April `06:45 IST`** | `send_fy_review` | Financial Year close annual wealth report |

---

## Project Structure

```text
finance/
├── pftracker/               # Project settings, OAuth discovery & ASGI gateway
│   ├── ai_gateway/          # Unified AI Gateway (multi-provider routing, circuit breakers, key pools)
│   ├── asgi.py              # Dual ASGI router (/mcp/sse FastMCP + Django HTTP)
│   ├── settings.py          # Django 6.0 configuration, CSP, security headers & logging
│   ├── urls.py              # Root URL configuration, OAuth 2.0 .well-known metadata & allauth blocks
│   └── utils.py             # Indian FY math (fy_start_year, fy_date_range), credential helpers
├── tracker/                 # Multi-tenancy, Monthly Savings, Goals, HRA & Notes
│   ├── models.py            # AccountGroup, User, HouseholdConfig, WebAuthnCredential, Transaction, HRAExpense, Note
│   ├── views.py             # Savings dashboard, HRA tracker, Notes CRUD, SSO login & dev-login
│   ├── context_processors.py# Global template context (role flags, household config)
│   └── templatetags/        # indian_numbers.py (indian_comma, compact_inr filters)
├── portfolio/               # Multi-Asset Wealth Tracker & AI DAG Engine
│   ├── models.py            # ZerodhaAccount, Stock/MF/FD/EPF/NPS/Cash/Bond/Crypto/Commodity/USStock/RealEstate/Goal
│   ├── dag.py               # 3-Stage Parallel/Sequential AI Portfolio Diagnostic DAG Engine
│   ├── ai.py                # Pydantic schemas, investor profile loader, macro research & email briefs
│   ├── sheets_sync.py       # Google Sheets gspread synchronization for Zerodha & holdings
│   ├── price_service.py     # Live Gold/Silver spot price & USD/INR exchange rate fetchers
│   └── views.py             # Master & Child (is_baby) portfolios, detail views, WebAuthn & vault gate
├── expenses/                # Automated Household Expense Intelligence
│   ├── models.py            # Expense, ExpenseCategory, PaymentSource, GmailAccount, CardStatement, StatementLine, MerchantRule, BrandKnowledge, ExpenseAuditRun
│   ├── services.py          # Unified facade re-exporting analytics, categories, ingestion & statements
│   ├── analytics.py         # Net spend math, month_summary, fy_summary, subscription_summary
│   ├── categories.py        # 4-tier categorization waterfall, AI batch categorizer & learn_category
│   ├── ingestion.py         # build_expense, PaymentSource auto-discovery & settle_internal_movements
│   ├── statements.py        # Encrypted PDF reader, 3-stage statement reconciler & refund matcher
│   ├── parsing.py           # Regex & structural parsers for 30+ Indian banks, UPI & EMI narrations
│   ├── gmail.py             # Gmail OAuth 2.0 flow, token refresh & incremental message sync
│   ├── ai.py                # AI categorization, statement line disambiguation & forensic FY audit
│   ├── crypto.py            # Fernet symmetric encryption for tokens, PDFs & passwords
│   └── views.py             # Monthly Bento feed, Annual FY review, Statement reconciler & Settings hub
├── jewellery/               # Physical Precious Metals & Ornament Vault
│   ├── models.py            # JewelleryItem, purity fineness factors & thumbnail cleanup signals
│   ├── utils.py             # HEIC/HEIF conversion & cached WebP thumbnail generator
│   └── views.py             # Vault gallery, live metal valuation & authenticated photo streaming
├── mcp_server/              # Model Context Protocol (MCP) Server
│   ├── server.py            # 30+ FastMCP read/write financial tools & audit helpers
│   ├── middleware.py        # MCPTokenAuthMiddleware (OAuth 2.0 PKCE, PRIMARY role & scope guard)
│   └── models.py            # MCPAuditLog with before/after JSON snapshots & rollback support
├── .agents/                 # Antigravity AI Agent Customizations
│   ├── rules/               # Modular architecture, financial precision, security & UI rules
│   └── skills/              # vault-architecture & codegraph skills
├── templates/               # Mobile-first DaisyUI 5 + Tailwind v4 templates (tracker, portfolio, expenses, jewellery)
└── static/                  # Compiled Tailwind CSS, vault-core.js, expenses.js, portfolio.js & PWA assets
```
