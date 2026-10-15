# Vault — Personal Finance Dashboard & Intelligence Hub

A production-grade personal finance, investment management, and household expense tracking platform built for the Indian financial ecosystem (April–March Financial Year, INR formatting, Gaj land units, gold/silver commodity pricing, EPF, NPS, Zerodha sync, and bank alert email scraping). Features an ASGI dual-architecture serving Django and a Model Context Protocol (MCP) server for autonomous AI agents.

---

## Features

- **Monthly Savings Tracker** — Set base annual/monthly goals, salary hike increments (`GoalIncrement`), one-off adjustments, carry-forward logic, and pace tracking per Indian FY (April–March).
- **HRA & Rent Tracker** — Track rent paid, landlord payment receipts, expense reconciliations, and revert balance tracking.
- **Portfolio Tracker** — Consolidated multi-asset tracking:
  - **Equity & Funds**: Zerodha holdings (Stocks, Index Mutual Funds, Active MFs) with automated Google Sheets sync.
  - **Fixed Income & Retirement**: EPF, NPS, and Fixed Deposits (with compound interest mathematics: simple, monthly, quarterly, annual).
  - **Cash & Bonds**: Liquid positions, bonds, and crypto.
  - **US Stocks & RSUs**: Dollar-denominated vested RSUs (e.g. Uber) with live USD/INR exchange rate conversion.
  - **Real Estate Assets**: Property tracking supporting North Indian land units (Gaj, Sq. Yards, Sq. Ft, Bigha, Acres), circle rates, holding CAGR, rental yields, and automated LLM prompt generation for micro-market research.
  - **Child Portfolio Segregation**: `is_baby` flag to cleanly isolate child investments ("Advay portfolio") from the master portfolio.
- **Jewellery Vault** — Precious metals inventory (Gold, Silver, Platinum, Diamonds) categorized by ornament type, purity multipliers, bank locker/home safe locations, and live valuations tied to commodity spot prices. Photo uploads support iPhone HEIC/HEIF auto-conversion.
- **AI Portfolio Insights & Multi-Stage DAG Engine** — Directed Acyclic Graph (DAG) workflow engine (`portfolio/dag.py`) executing specialized diagnostic lenses (Allocation & Liquidity, Asset Quality & Legacy Fund Audit, Macro Regime & Crash Stress), cross-pillar strategy with Indian FY 2026-27 tax optimization (Section 112A LTCG harvesting, Section 54/54EC real estate indexation choices), and mathematically grounded composite health scoring ($0.30 \times S_{\text{allocation}} + 0.25 \times S_{\text{quality}} + 0.25 \times S_{\text{strategy}} + 0.20 \times S_{\text{macro}}$).
- **Unified AI Gateway** — Centralized AI routing hub (`pftracker/ai_gateway`) supporting Shakti Cloud (DeepSeek-R1, LLaMA 3.3) and Google Gemini (Gemini 4 Argon, Gemini 3.8 Flash). Features multi-node load balancing, multi-key rotation pools on HTTP 429 rate limits, circuit breakers, and automatic Dev vs. Prod model selection (`DEBUG=True` uses fast/free models).
- **Model Context Protocol (MCP) Server** — Native `/mcp` ASGI endpoint exposing read resources and write tools with OAuth 2.0 PKCE authentication and full before/after audit rollback logs (`MCPAuditLog`).
- **CodeGraph Intelligence** — Built-in local code knowledge graph (AST-level symbol indexing, call hierarchies, blast-radius impact analysis) integrated with Antigravity IDE.
- **Bank-Grade Security** — WebAuthn biometric unlock (Face ID / Touch ID), portfolio session TTL, Fernet encryption for tokens and passwords, strict CSP, and automated GCS backups.

---

## User Roles & Access Control

Vault enforces strict multi-tenancy scoped to an `AccountGroup` with granular feature toggles managed in `HouseholdConfig`:

| Module | Primary Account Holder (`PRIMARY`) | Account Holder (`ACCOUNT_HOLDER`) | Landlord (`LANDLORD`) |
| :--- | :--- | :--- | :--- |
| **Savings Dashboard** | Full CRUD | View only | No access |
| **HRA & Rent** | Full CRUD | Full CRUD | View only (Rent records) |
| **Portfolio Tracker** | Full access (`_vault_gate`) | No access | No access |
| **Jewellery Vault** | Full access (`_vault_gate`) | Full access (`_vault_gate`) | No access |
| **Expense Tracker** | Full access (all spend) | Full access (investments masked) | No access |
| **Notes** | Full CRUD | Full CRUD | No access |
| **MCP Server Tools** | Full access | No access | No access |
| **Admin & Monitor** | Superuser only | No access | No access |

> [!NOTE]
> Portfolio and Jewellery are gated behind `_vault_gate`, requiring the household password or WebAuthn biometric unlock with a 30-minute session TTL.

---

## Tech Stack

- **Backend**: Python 3.14, Django 6.0, Starlette (ASGI router)
- **Application Server**: Gunicorn with `uvicorn.workers.UvicornWorker`
- **Database**: PostgreSQL (production via `dj-database-url`) / SQLite (development)
- **Frontend & Design**: Tailwind CSS v4, DaisyUI v5, dark-first glassmorphism (`night` theme), Chart.js 4.4, Inter font, Material Symbols Outlined
- **AI & Code Intelligence**: Google GenAI SDK (`google-genai`), CodeGraph MCP (`@colbymchenry/codegraph`)
- **Authentication**: Django AllAuth (Google SSO), WebAuthn 2.0, Django OAuth Toolkit (MCP OAuth)
- **Storage & Ingestion**: Google Cloud Storage (backups), `gspread` (Sheets), `pypdf` (statement decryption), `cryptography` (Fernet)

---

## Local Development Setup

### 1. Prerequisites
Ensure Python 3.14+ and Node.js 20+ are installed:
```bash
python3 --version
node -v
```

### 2. Virtual Environment & Dependencies
```bash
python3.14 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment & Database Configuration
```bash
cp .env.example .env
python manage.py migrate
python seed_data.py
```

### 4. CodeGraph & Pre-Commit Setup
Install CodeGraph and setup pre-commit hooks:
```bash
npm install -g @colbymchenry/codegraph
codegraph init
./scripts/pre-commit
```

### 5. Run Development Server
```bash
python manage.py runserver
```

Open `http://localhost:8000/`. In development mode (`DJANGO_DEBUG=True`), use the Dev Mode dropdown on the login page to sign in as:
- **`atul`** (Primary Account Holder / Admin)
- **`spouse`** (Account Holder)
- **`landlord`** (Landlord)

---

## CodeGraph & Agent Guidelines

Vault includes full native support for **Google Antigravity** and agentic workflows:

- **CodeGraph Knowledge Graph**: The index lives in `.codegraph/` (2,200+ nodes, 5,000+ edges). Query symbols, explore call graphs, and evaluate impact:
  ```bash
  codegraph query get_portfolio_summary
  codegraph explore "vault gate authorization"
  codegraph impact fy_start_year
  codegraph sync
  ```
- **Rules & Guidelines**:
  - `GEMINI.md` / `AGENTS.md`: Core system instructions and security protocols.
  - `.agents/rules/`: Modular guidelines for CodeGraph navigation, financial precision, security, and UI design.
  - `.agents/skills/`: Executable skills for `codegraph` and `vault-architecture`.
  - `.agents/hooks.json`: Lifecycle hooks enforcing pre-tool safety guards and automatic post-edit CodeGraph synchronization.

---

## AI Intelligence & Multi-Stage DAG Architecture

Vault uses a specialized **Directed Acyclic Graph (DAG) Workflow Engine** (`portfolio/dag.py`) backed by the **Unified AI Gateway** (`pftracker/ai_gateway`):

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

### Deterministic Financial Health Scoring
To eliminate the score hallucinations common in single-shot prompts, the final 0–100 score is computed mathematically:
$$\text{Health Score} = \text{round}(0.30 \times S_{\text{allocation}} + 0.25 \times S_{\text{quality}} + 0.25 \times S_{\text{strategy}} + 0.20 \times S_{\text{macro}})$$
Clamped between 0 and 100.

### AI Gateway Features (`pftracker.ai_gateway`)
- **Multi-Provider & Multi-Node Routing**: Primary / fallback routing across Shakti Cloud (`deepseek-r1`, `llama3_3`) and Google Gemini (`gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.1-pro-preview`).
- **Resilient Key Rotation Pools**: Automatic round-robin rotation upon HTTP 429 rate limits with 60-second cooldowns.
- **Circuit Breaker Protection**: Consecutive node failures trip circuits to `OPEN` to prevent cascading latency spikes.
- **Dev vs. Prod Model Tiering**: When `DJANGO_DEBUG=True`, automatically selects lightweight/fast models (`gemini-3.8-flash`) for near-zero development costs. In production, leverages frontier reasoning models (`gemini-4-argon` / `deepseek-r1`).

---

## Management Commands

| Command | Description |
| :--- | :--- |
| `test_shakti_ai` | Pings Shakti Cloud / DeepSeek, verifies streaming, or benchmarks DAG scoring |
| `refresh_prices` | Scrapes latest gold (24K) and silver spot prices from goodreturns.in |
| `sync_sheets` | Syncs Zerodha holdings and mutual funds from Google Sheets |
| `take_snapshot` | Captures monthly asset and return snapshot for net-worth tracking |
| `appreciate_land` | Applies annual FY-end land capital appreciation (+6%) |
| `send_monthly_summary` | Dispatches monthly portfolio AI summary email |
| `send_weekly_brief` | Generates and emails the Sunday Equity Intelligence Brief |
| `send_fy_review` | Generates the annual FY close portfolio review email |
| `sync_expenses [--email X]` | Ingests new bank/card alerts from connected Gmail accounts |
| `expense_reminders` | Emails credit card bill payment reminders (5-day, 1-day, due-day) |
| `send_expense_summary` | Emails monthly household spending report |
| `backup_db --bucket NAME` | Dumps PostgreSQL, gzips archive, and uploads to GCS |
| `run_mcp_server` | Runs the MCP server in stdio mode for local CLI agents |

---

## Scheduled Tasks (Cron)

Recommended production schedule (`CRON_TZ=Asia/Kolkata`):

| Schedule | Task / Command | Purpose |
| :--- | :--- | :--- |
| **Hourly at :17** | `sync_expenses` | Ingest Gmail bank & card alert emails |
| **Daily 6:00 AM IST** | `sync_sheets` && `refresh_prices` | Sync Zerodha holdings & refresh commodity rates |
| **Daily 9:00 AM IST** | `expense_reminders` | Credit card bill payment reminders |
| **Daily 11:30 PM IST** | `backup_db` | PostgreSQL database dump to GCS |
| **Sunday 6:30 AM IST** | `send_weekly_brief` | Weekly Equity Intelligence Brief email |
| **1st of Month 5:45 AM IST** | `appreciate_land` | Annual April 1 land value adjustments |
| **1st of Month 6:00 AM IST** | `take_snapshot` | Monthly portfolio net-worth snapshot |
| **1st of Month 6:30 AM IST** | `send_monthly_summary` | Monthly AI portfolio review email |
| **1st of Month 8:00 AM IST** | `sync_expenses` && `send_expense_summary` | Monthly household expense report |
| **1st of April 6:45 AM IST** | `send_fy_review` | Financial Year close annual report |

---

## Project Structure

```
finance/
├── pftracker/               # Project configuration & ASGI gateway
│   ├── ai_gateway/          # Unified AI Gateway (routing, circuit breakers, Shakti & Gemini)
│   ├── asgi.py              # Starlette ASGI router (/mcp + Django /)
│   ├── settings.py          # Django 6.0 settings & security policies
│   ├── utils.py             # Indian FY math, precision helpers, credentials
│   └── adapters.py          # Custom AllAuth Google SSO whitelist adapter
├── tracker/                 # Monthly savings, goals, HRA & notes
│   ├── models.py            # User, AccountGroup, HouseholdConfig, Transaction, Note
│   ├── services.py          # Carry-forward logic, savings pace, FY calculations
│   └── views.py             # Savings dashboard, HRA tracker, notes endpoints
├── portfolio/               # Investments, Zerodha, FDs, Real Estate & AI
│   ├── models.py            # ZerodhaAccount, Holdings, FDs, RealEstate, Goals
│   ├── services.py          # Portfolio valuation, compounding, Sheets sync
│   ├── dag.py               # Multi-stage DAG workflow engine for portfolio diagnostics
│   ├── ai.py                # Gemini & Shakti API caller, prompts, schemas, fallbacks
│   └── views.py             # Master portfolio, Advay baby portfolio, WebAuthn unlock
├── jewellery/               # Precious metals vault
│   ├── models.py            # JewelleryItem (Gold, Silver, Platinum), purity factors
│   └── views.py             # Vault gallery, dynamic valuation, HEIC upload handler
├── expenses/                # Automated expense tracker
│   ├── parsing.py           # Regex parser for 30+ Indian banks & UPI alerts
│   ├── statements.py        # PDF statement parser (pypdf) & reconciliation
│   ├── anomaly.py           # Median/MAD suspicious transaction detection
│   └── sync.py              # Multi-inbox Gmail OAuth synchronization
├── mcp_server/              # Model Context Protocol integration
│   ├── server.py            # MCP resources and write tools
│   ├── oauth.py             # PKCE OAuth token validator
│   └── audit.py             # Before/after JSON audit logs & one-click reverts
├── .agents/                 # Antigravity agent customizations
│   ├── mcp_config.json      # CodeGraph MCP server configuration
│   ├── hooks.json           # Safety gates & automatic CodeGraph sync hooks
│   ├── rules/               # Modular architecture, financial, and UI rules
│   └── skills/              # codegraph & vault-architecture skills
├── scripts/                 # Pre-commit hooks, deployments, and backup scripts
├── templates/               # DaisyUI 5 / Tailwind HTML templates
└── static/                  # CSS design tokens, Chart.js scripts, PWA manifest
```

---

## Security & Privacy Guidelines

- **Never commit credentials**: `.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, and service account JSON files are gitignored.
- **Pre-Commit Enforcement**: The pre-commit hook (`scripts/pre-commit`) automatically blocks any commit containing secret filenames or private keys.
- **Token Security**: Gmail OAuth tokens and statement passwords are stored encrypted in the database using Fernet keys.
