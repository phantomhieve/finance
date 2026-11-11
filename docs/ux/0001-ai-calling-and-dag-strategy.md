# ADR-0001: Unified AI Gateway Tiering and Quant-Grounded Parallel DAG Architecture

## Status
Accepted

## Date
2026-11-11

## Context

Vault executes LLM workflows across three core financial domains, all routed through `pftracker/ai_gateway/`:

1. **Multi-Stage Portfolio Intelligence (`portfolio/dag.py`, `portfolio/ai/`)**: Evaluates an 11-asset-class Indian household balance sheet (Stocks, Active & Direct Mutual Funds, US RSUs, EPF/PF/NPS, Fixed Deposits, Physical Gold/Silver, Cash, Bonds, Crypto, and Gaj/Bigha Real Estate), producing a `0–100` composite health score and `8–14` actionable insights.
2. **Annual FY-End Land Appraisal (`portfolio/land_appraisal.py`)**: Runs on April 1 (`deploy/cron`) ahead of the March FY-close snapshot to value illiquid plot and agricultural holdings using search-grounded market comparables, government circle rates, macro indicators, and conservative fiduciary haircuts.
3. **High-Frequency Expense Intelligence (`expenses/ai/`)**: Performs daily batch transaction categorization (`ai_categorize_day`), bank alert and receipt extraction, multi-page credit card PDF statement fallback extraction, 3-stage statement candidate disambiguation, monthly spend commentary, and forensic FY anomaly detection.

Key architectural constraints:
- **Zero LLM Arithmetic Drift**: Monetary ratios, concentration indices, crash drawdowns, tax harvesting thresholds, and valuation haircuts must be computed in Python `decimal.Decimal` before any prompt runs.
- **Cost & Latency Discipline**: Interactive and batch diagnostics must keep end-to-end latency low while reserving frontier reasoning tokens strictly for cross-pillar strategy, editorial synthesis, and annual fiduciary valuation.
- **Multi-Tenant & Untrusted-Input Safety**: Prompts processing external emails, receipts, and PDF statements must strip Indian financial PII, prevent XML tag breakouts, and isolate household cache entries by `AccountGroup`.
- **Provider & Socket Fault Tolerance**: Single API key rate limits (`HTTP 429`), provider outages (`HTTP 5xx`), or stalled upstream sockets must never fail a cron job or block web workers indefinitely.

---

## Decision

### 1. Declarative Unified AI Gateway & Model Tiering (`pftracker/ai_gateway/`)

All LLM calls resolve through `AIConfigRegistry` (`pftracker/ai_gateway/config.py`) using typed `TaskProfile` specifications (`DEFAULT_TASK_SPECS`):

| Workload Tier | Task Profiles | Production (`DJANGO_DEBUG=False`) | Development (`DJANGO_DEBUG=True`) |
| :--- | :--- | :--- | :--- |
| **Frontier Reasoning & Search** | `PORTFOLIO_INSIGHTS`, `PORTFOLIO_DAG_STRATEGY`, `PORTFOLIO_DAG_SYNTHESIS`, `LAND_APPRAISAL_COMPS` *(Search Grounded)*, `LAND_APPRAISAL_AUDIT`, `LAND_APPRAISAL_SYNTHESIS` | `gemini-4-carbon` (`ThinkingLevel.HIGH`) | `gemini-3.8-flash` (`LOW`) for portfolio; `gemini-2.5-flash-lite` (`LOW`) for land appraisal |
| **Digest & Commentary** | `WEEKLY_BRIEF`, `MONTHLY_EXPENSE_NOTE` | `gemini-3.8-flash` (`ThinkingLevel.HIGH`) | `gemini-3.8-flash` (`ThinkingLevel.LOW`) |
| **Fast Specialist Lenses & Extraction** | `PORTFOLIO_DAG_ALLOCATION`, `PORTFOLIO_DAG_QUALITY`, `PORTFOLIO_DAG_MACRO`, `EXPENSE_CATEGORIZATION`, `RECEIPT_PARSING`, `STATEMENT_PARSING`, `STATEMENT_MATCHING`, `EXPENSE_ANOMALY` | `gemini-3.8-flash` (`thinking_budget=0`) | `gemini-2.5-flash-lite` (`thinking_budget=0`) |

- **Override Precedence**: Explicit call kwargs > `AI_TASK_MODEL_<PROFILE>` > domain environment variable (`GEMINI_MODEL` for `REASONING`/`RESEARCH` portfolio & land profiles; `EXPENSES_GEMINI_MODEL` for expense, receipt, statement, and digest profiles) > `TaskSpec` default.
- **Cascade Failover & Key Rotation**: `NodeRouter` and `CircuitBreakerManager` route across configured provider nodes (`gemini-cloud` and `shakti-primary` OpenAI-compatible `deepseek-r1` / `llama3_3`), rotating across healthy API keys on `HTTP 429` (`60s` per-key cooldown) and translating model families automatically during cross-provider failover.
- **Outbound Sanitization & Nonced XML Boundaries (`pftracker/ai_gateway/sanitizer.py`, `gateway.py`)**:
  - `mask_pii()` redacts Indian PAN, Aadhaar, phone numbers, bank account numbers, OTP/PIN codes, email addresses, and card numbers (preserving `[CARD_...4444]` last-4 digits for statement matching).
  - `mask_secrets()` strips API keys and Bearer tokens from logs and exception traces.
  - When `use_boundary_tags=True` (enabled across all untrusted expense/receipt/statement profiles), `AIGateway` unconditionally runs `detect_prompt_injection()`, escapes embedded angle brackets, and wraps untrusted text inside a per-call random-nonced XML tag (`<user_payload_<hex>>...</user_payload_<hex>>`) referenced in the `system` boundary instruction.

---

### 2. Portfolio Quant-Grounded Parallel DAG (`portfolio/dag.py`)

```
Household Portfolio Snapshot + Investor Profile (main thread)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage 0: Deterministic Python Quant Engine (Decimal, <5ms, 0 tokens)    │
│ • Equity & asset-class HHI, >5% / >10% stock flags across ALL holdings  │
│ • Full-universe top gainers, worst losers, & <=-15% loss-aversion flags │
│ • Tier 1/2/3 liquidity (excluding 'lent' cash) & 6m emergency coverage  │
│ • FD post-tax yield vs 8.15% EPF hurdle & CPI real-yield spread         │
│ • Exact -35% equity crash INR, -30% RSU shock INR, & 6m momentum trend  │
│ • Section 112A ₹1.25L harvestable LTCG & per-goal rupee shortfalls      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Typed PortfolioQuantMetrics + Surgical Slices
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ Node 1A (Flash)   │   │ Node 1B (Flash)   │   │ Node 1C (Flash)   │
│ Allocation & Liq. │   │ Quality & MF Audit│   │ Macro & Crash     │
│ AllocationLens    │   │ QualityLens       │   │ MacroStressLens   │
└─────────┬─────────┘   └─────────┬─────────┘   └─────────┬─────────┘
          │ (Bounded stage_timeout; per-node Decimal-grounded fallback)
          └───────────────────────┼───────────────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ Stage 2 (gemini-4-carbon HIGH)│
                  │ Tax & Rebalancing Strategy    │
                  │ StrategyLensResult            │
                  └───────────────┬───────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ Stage 3 (gemini-4-carbon HIGH)│
                  │ Executive Editorial Synthesis │
                  └───────────────┬───────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Deterministic Critic & Grounding Reducer                                │
│ • Enforces S = round(0.30*Alloc + 0.25*Qual + 0.25*Strat + 0.20*Macro)  │
│ • Deduplicates titles, backfills dropped critical/pillar insights       │
│ • Attaches DAGExecutionMetadata (nodes, degraded_nodes, quant summary)  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Typed Pydantic Contracts**: Every stage validates against strict schemas (`AllocationLensResult`, `QualityLensResult` with `list[LegacyFundAuditItem]`, `MacroStressLensResult`, `StrategyLensResult`, `PortfolioInsightsResponse`).
- **Leak-Free Bounded Parallelism**: Sync execution (`PortfolioInsightsDAG.execute`) runs Stage 1 on `DjangoSafeThreadPoolExecutor(max_workers=3)` with bounded `stage_timeout` (`PORTFOLIO_DAG_STAGE_TIMEOUT`, default `90s`) and non-blocking `shutdown(wait=not timed_out, cancel_futures=True)`; async execution (`execute_async`) uses `asyncio.gather` over `agenerate_structured`.
- **Multi-Tenant Stage Checkpointing**: When `PORTFOLIO_DAG_STAGE_CACHE=true`, completed stage outputs are memoized under `sha256(stage_name + group_id + slice_payload + investor_profile)` for `PORTFOLIO_DAG_STAGE_CACHE_TTL` seconds (`600s` default).

---

### 3. Land Appraisal 3-Stage Fiduciary DAG (`portfolio/land_appraisal.py`)

1. **Unit Normalization & Fiduciary Haircut Math (`compute_fiduciary_haircuts`)**:
   - Normalizes all land parcels to Sq. Yards via `holding.area_in_gaj` (`GAJ`, `SQYD`, `SQFT`, `ACRE`, `BIGHA`, `SQMT`).
   - Computes exact `Decimal` haircuts:
     - **Speculative Ask Haircut (`SAH`)**: `30%` discount on portal broker asks to approximate registered deed values.
     - **Dynamic Illiquidity & Friction Discount (`IFD`)**: `max(15.0%, 9.0% + 0.75 * repo_rate)` for `6–12` month exit friction and stamp/legal costs.
     - **Execution Slippage Penalty (`ESP`)**: `min(10.0%, (delay_months // 6) * 2.5%)` for corridor infrastructure delays.
     - **Macro YoY Growth Cap**: `repo_rate + cpi_inflation + 3.0%` illiquidity premium.
2. **Stage 1 (`LAND_APPRAISAL_COMPS`)**: `gemini-4-carbon` (`TaskType.RESEARCH`) with Google Search grounding extracts circle rates, registry trends, portal asks, CPI/repo context, and corridor milestone status.
3. **Stage 2 (`LAND_APPRAISAL_AUDIT`) & Stage 3 (`LAND_APPRAISAL_SYNTHESIS`)**: `gemini-4-carbon` (`ThinkingLevel.HIGH`) audits valuation assumptions and synthesizes the balance sheet adjustment. Python clamps `recommended_appreciation_pct` strictly to `0% <= pct <= min(15.0%, macro_cap, auditor_ceiling)`, reconciles `new_valuation_inr`, `net_value_increase_inr`, `implied_rate_per_sq_yd_inr`, and `unrealized_speculative_buffer_inr` to `Decimal('0.01')`, and dispatches the valuation certificate (`templates/emails/land_appraisal.html`).

---

### 4. Expense Batch Deduplication & Parallel Statement Extraction (`expenses/ai/`)

- **Canonical Merchant Deduplication (`categorise`)**: Groups input transactions by normalized `(merchant_signature, direction, channel)` before chunking into `MAX_BATCH = 40`, fanning validated `(category, confidence)` assignments back across matching IDs and normalizing case/whitespace against `allowed_categories`.
- **Parallel PDF Statement Extraction (`extract_statement_lines`)**: Processes multi-chunk statement PDFs concurrently across `DjangoSafeThreadPoolExecutor(max_workers=3)` while preserving page ordering and per-chunk fault isolation.

---

## Consequences & Operational Invariants

- **Deterministic Financial Integrity**: LLMs interpret pre-computed `Decimal` metrics and return typed qualitative/strategic recommendations; Python owns every balance-sheet figure, composite score, and ceiling clamp.
- **Explicit Expense Floor Assumption**: When `portfolio/investor_profile.md` omits an explicit monthly household burn figure, Stage 0 applies a conservative `₹75,000/month` (`₹4,50,000` 6-month emergency floor) and records that assumption explicitly in `PortfolioQuantMetrics`.
- **Search Grounding + Schema Fallback**: If an upstream Gemini endpoint rejects `GoogleSearch` tools paired with `response_schema`, `GeminiAdapter.generate_structured()` automatically retries with structured schema validation so Stage 1 land discovery completes cleanly.
