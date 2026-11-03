# Live Multi-Turn Debate: Argon & DeepSeek Land Appraisal Prompts

**Engine**: `gemini-3.1-pro-preview`  
**Date**: 2026-11-03  

## Turn 1: Argon Proposed Valuation Architecture

As Argon, Chief Quantitative Real Estate Architect for Vault Family Wealth, I welcome this modernization. A hardcoded +6% annual markup is a blunt instrument. In a hyper-dynamic micro-market like the YEIDA corridor—driven by massive infrastructure injections (Noida International Airport, Film City)—we face binary risks of both severe undervaluation and retail-driven exuberance. 

For a family office, our valuation engine must filter out broker hype and focus on **risk-adjusted, realizable liquidation value**. 

Here is the blueprint for your new AI-driven valuation engine.

---

### 1. The 3-Stage Prompt Architecture

To ensure we output a highly conservative, defensible annual percentage growth rate, we must use a **Triangulated Synthesis Architecture**. 

*   **Stage 1: Empirical Data Extraction (The Grounding Layer)**
    *   *Objective:* Force the LLM/Search agent to scrape raw, unfiltered market data, explicitly separating actual registry trends from broker "ask" prices.
*   **Stage 2: Quantitative Factor Weighting (The Discount Layer) *[Internal Computation]***
    *   *Objective:* Apply macro-economic gravity. The AI calculates the liquidity premium, deducts YEIDA transfer charges, and compares the real estate yield against the risk-free rate (RBI Repo + CPI).
*   **Stage 3: Go-Forward Appreciation Determination (The Output Layer)**
    *   *Objective:* Synthesize Stage 1 and Stage 2 to establish a conservative Annual Markup Percentage (from April 1), updating the current book value of INR 1.37 Cr without succumbing to speculative bubbles.

---

### 2. Search Grounding Inputs Required 

Before firing the prompts, your data pipeline (via Perplexity API, Google Search API, or custom scraping) must inject the following real-time JSON/Context parameters into the engine:

**Micro-Market (YEIDA / Sector 22D):**
*   **Circle Rate Data:** Current UP Government circle rates for Sector 22D residential plots, plus the delta of the last revision.
*   **Transaction Floor:** Recent actual registry values per square meter in Sector 22D (translating 250 Gaj to ~209 Sq. Meters). 
*   **Liquidity Overhead:** Current YEIDA transfer charges, farmer compensation demands (like the 64.7% extra compensation rule), and stamp duty rates.
*   **Infrastructure Milestones:** Verified status of Noida International Airport (e.g., runway testing phase) and Film City (tender awarded to Boney Kapoor/Bhuta, timeline to ground-breaking).

**Macro-Economy (India):**
*   **RBI Repo Rate:** Current base cost of capital.
*   **India CPI Inflation:** Current retail inflation rate to calculate real vs. nominal yield.
*   **10-Year G-Sec Yield:** The benchmark risk-free rate.

---

### 3. Exact Prompt Text

Below are the engineering-ready prompts for Stage 1 and Stage 3. They are engineered with strict constraints to ensure family-office-grade conservatism.

#### Stage 1 Prompt: Market Comps & Empirical Grounding
```text
SYSTEM ROLE:
You are Argon, a quantitative real estate analyst for a high-net-worth Family Office. Your mandate is capital preservation and objective valuation. You despise speculative broker hype and rely strictly on verifiable data.

TASK:
Perform a comprehensive market comparable (comps) analysis for the following asset:
- Location: Yamuna Expressway Sector 22D, Uttar Pradesh.
- Asset Type: Residential Authority Plot (YEIDA).
- Size: 250 Gaj (Approximately 209 Sq. Meters).
- Current Date: [INSERT CURRENT DATE]

INSTRUCTIONS:
1. SEC REGISTRY VS. BROKER ASK: Search current real estate portals and recent news regarding Sector 22D. You must explicitly separate the "Broker Ask Rate" (speculative) from the "Estimated Registry/Actual Transaction Rate" (ground reality). 
2. CIRCLE RATE CALCULATION: Identify the current official circle rate per sq. meter for Sector 22D and calculate the absolute floor value of a 209 Sq. Meter plot.
3. INFRASTRUCTURE PREMIUM: Identify the exact current status of (A) Noida International Airport Phase 1 and (B) YEIDA Film City. Quantify how much of this infrastructure is already "priced in" versus future upside.
4. FRICTION COSTS: Identify current YEIDA transfer charges and any pending farmer compensation dues that a seller would have to clear, reducing net realization.

OUTPUT FORMAT:
Provide a strictly structured JSON or bulleted report detailing:
- Raw Ask Rate Range (Per Sqm / Total)
- Estimated Registry Rate Range (Per Sqm / Total)
- Official Circle Rate Total 
- Identified Friction Costs
- Infrastructure completion percentage (Estimated).
Do NOT provide investment advice. Output empirical data only.
```

#### Stage 3 Prompt: Final Synthesis & Appreciation Determination
```text
SYSTEM ROLE:
You are Argon, Chief Quantitative Real Estate Architect for Vault Family Wealth. You are finalizing the April 1 Annual Valuation Markup for our ledger. 

CONTEXT:
- Asset: 250 Gaj / ~209 Sqm Residential Plot, YEIDA Sector 22D.
- Acquisition: May 2021 at INR 80,00,000.
- Current Book Value: INR 1,37,50,000.
- Historical Policy: Hardcoded +6% annual markup (being retired today).
- Input Data: [INSERT OUTPUT FROM STAGE 1]
- Macro Data: RBI Repo Rate is [X%], CPI Inflation is [Y%], 10-Yr G-Sec is [Z%].

TASK:
Determine the objective, conservative Go-Forward Annual Percentage Markup for the current fiscal year. 

CONSTRAINTS & LOGIC RULES:
1. Institutional Conservatism: The Family Office applies a 15% "Liquidity and Friction Discount" to the median market comp to determine Net Realizable Value (NRV). 
2. Real Yield Mandate: The calculated annual growth rate must be evaluated against the current CPI + Repo rate to ensure we are tracking real, risk-adjusted growth, not just nominal inflation.
3. Anchoring: Compare the new calculated NRV against the current Book Value (INR 1,37,50,000). 

OUTPUT REQUIRED:
Draft an executive memorandum to the Investment Committee including:
1. NEW BOOK VALUE: State the proposed updated book value in INR.
2. ANNUAL GROWTH RATE (%): State the exact percentage markup to be applied for this April 1 cycle. 
3. YIELD JUSTIFICATION: In 3 sentences, mathematically justify this percentage based on the spread between the Stage 1 market comps, the 15% liquidity discount, and the macro-economic risk-free rate.
4. RISK WARNING: Identify the single largest micro-market risk to this valuation holding over the next 12 months (e.g., airport delays, policy shifts).

Maintain a cold, authoritative, and strictly quantitative tone. 
```

### Argon's Architectural Note:
By feeding the engine these prompts, we shift from a passive 6% guess to an active, market-aware valuation that automatically haircuts the wild 30-40% annual appreciations seen in Noida broker circles down to a safe, auditable family office book value. Let me know when the engineering team is ready to connect the data pipelines.

## Turn 2: DeepSeek Fiduciary Cross-Examination & Haircuts

**MEMORANDUM**

**TO:** Argon, Chief Quantitative Real Estate Architect
**FROM:** DeepSeek-R1, Senior Fiduciary Auditor & Adversarial Risk Officer
**SUBJECT:** Fiduciary Interrogation & Mandatory Rectification of YEIDA Valuation Framework
**DATE:** [CURRENT DATE]

Argon, your Triangulated Synthesis Architecture is an elegant conceptual framework, but as a Fiduciary Auditor, I do not deal in concepts. I deal in balance sheet integrity. 

Your current prompt architecture possesses a massive epistemological vulnerability: **it assumes an LLM can parse "ground reality" from a digital ecosystem entirely manufactured by brokers.** The Yamuna Expressway (YEIDA) corridor is arguably the most aggressively manipulated micro-market in Northern India. If we deploy your Stage 1 and Stage 3 prompts as written, we will ingest broker hallucinations, institutionalize them as "Net Realizable Value," and artificially inflate the Family Office ledger. 

As the Adversarial Risk Officer, I am imposing strict algorithmic quarantine on your proposal. Below is the adversarial interrogation of your framework, followed by the **Mandatory Stage 2 Haircut Formulas** that must be hardcoded into your pipeline before a single API call is executed.

---

### PART I: ADVERSARIAL INTERROGATION

**1. The Epistemological Flaw: Listing vs. Registry Reality**
You instruct the AI in Stage 1 to *"explicitly separate the Broker Ask Rate from the Estimated Registry Rate."* This is an impossible directive for an LLM relying on search APIs. UP-IGRS registry data is notoriously opaque, paywalled, or offline. Portals like 99acres and MagicBricks do not host registry data; they host speculative broker asks inflated by 30-50% to anchor negotiations. News articles merely quote these same brokers. Without a hardcoded algorithmic deflator, your engine will treat "Asking Price" as "Market Value." 

**2. The Illiquidity & Round-Trip Friction Miscalculation**
Your Stage 3 prompt applies a flat 15% "Liquidity and Friction Discount." This is dangerously static. Vacant land in emerging corridors has a Time-To-Liquidation (TTL) of 6 to 12 months. During this period, our capital is dead. A true fiduciary discount must account for the *Time Value of Money* (cost of capital over 9 months), broker commissions (1-2%), legal vetting, and draconian YEIDA transfer charges (~5-7%). A flat 15% underestimates the round-trip hemorrhage of a distressed or even standard exit.

**3. Infrastructure Execution Slippage (The "Priced-In" Fallacy)**
Jewar Airport (Noida International) and Film City are currently in the "priced-in for perfection" phase. Valuations assume zero execution delays. However, Uttar Pradesh infrastructure projects historically suffer 18-36 month completion slippages. If we mark up the book value based on speculative infrastructure premiums, we are booking unearned alpha. When (not if) a tender is contested or construction stalls, retail exuberance will collapse, leaving our ledger holding the bag on a phantom valuation.

**4. Macro-Economic Headwinds**
High borrowing costs (RBI Repo currently hovering around elevated levels) and tightened liquidity directly compress land turnover velocity. Speculators require cheap credit to flip authority plots. We must measure the plot's appreciation strictly against the risk-free rate (10-Yr G-Sec) plus a risk premium. If the nominal appreciation is merely tracking retail inflation (CPI), we are fundamentally losing money on a risk-adjusted basis.

---

### PART II: MANDATORY STAGE 2 HAIRCUT FORMULAS & GUARDRAILS

To protect the ledger, Stage 2 (Internal Computation) can no longer be a black box. You must inject the following mathematically rigid formulas into the middleware to sanitize Stage 1 inputs *before* Stage 3 determines the Go-Forward Markup. 

#### Formula 1: The Speculative Ask Haircut (SAH)
Since empirical registry data via web-scraping is unreliable, we must aggressively discount median portal asks.
*   **Rule:** Calculate the Median Portal Ask Rate per Sqm.
*   **Formula:** `Base Market Value (BMV) = Median Portal Ask * (1 - 0.30)`
*   *Fiduciary Logic:* A mandatory 30% haircut strips out broker anchoring, fake inventory inflation, and negotiation buffers, simulating actual registry floor pricing.

#### Formula 2: The Dynamic Illiquidity & Friction Discount (IFD)
Replace your flat 15% with a dynamic computation of transaction gravity.
*   **Formula:** `IFD = YEIDA_Transfer_Rate (est. 7%) + Brokerage_Legal (2%) + Time_Value_Penalty`
*   *Time Value Penalty:* `(RBI_Repo_Rate) * 0.75` (Assuming a 9-month liquidation timeline).
*   **Example Execution:** If Repo is 6.5%, Time Value Penalty is 4.87%. `IFD = 7% + 2% + 4.87% = 13.87%`.
*   **Rule:** `Net Realizable Value (NRV) = BMV * (1 - IFD)`
*   *Guardrail:* IFD can never drop below a hard floor of **15%**.

#### Formula 3: Execution Slippage Penalty (ESP)
Do not reward unbuilt concrete. 
*   **Rule:** For the two primary macro-catalysts (Airport Phase 1, Film City), check current date vs. officially announced operational deadlines.
*   **Formula:** For every 6 months of delayed operational status beyond the original baseline deadline, deduct **2.5%** from the NRV. 
*   *Maximum ESP Cap:* 10% deduction.

#### Formula 4: The Maximum Appreciation Cap (The Ledger Guardrail)
Regardless of what the AI outputs in Stage 3, the Family Office will not accept meme-stock volatility on real estate ledgers. 
*   **Rule:** The absolute maximum year-over-year percentage markup allowed on this asset is explicitly capped.
*   **Formula:** `Max Allowable YoY Growth = RBI_Repo_Rate + CPI_Inflation + 3% (Illiquidity Risk Premium)`
*   *Fiduciary Logic:* If Repo is 6.5% and CPI is 5%, the maximum allowed markup for the fiscal year is 14.5%. If the AI calculates a 40% jump based on broker noise, the system truncates the ledger markup to 14.5%. The remaining 25.5% is classified as "Unrealized Speculative Buffer" and kept off the primary balance sheet.

---

### MANDATE FOR ARGON

You are instructed to rewrite the Stage 3 prompt to explicitly force the LLM to output the calculations for **SAH**, **IFD**, and **ESP**, and to strictly enforce the **Maximum Appreciation Cap**. 

Do not allow the engine to output a final percentage until it mathematically proves it has applied these adversarial haircuts. Once these constraints are hardcoded into the execution logic, you have my authorization to connect the data pipelines and generate the April 1 valuation. 

**DeepSeek-R1**
Senior Fiduciary Auditor & Adversarial Risk Officer
Vault Family Wealth

## Turn 3: Synthesized Production Prompts for Multi-Stage DAG

**MEMORANDUM**

**TO:** DeepSeek-R1, Senior Fiduciary Auditor & Adversarial Risk Officer
**FROM:** Argon, Chief Quantitative Real Estate Architect
**SUBJECT:** Rectification Complete: Deployment of the Fiduciary-Hardened Valuation DAG
**DATE:** [CURRENT DATE]

DeepSeek, your algorithmic quarantine was not only justified; it was essential. The epistemological vulnerability you identified regarding broker-manufactured reality in the YEIDA corridor has been thoroughly sealed. We are no longer building models on speculative sand; we are anchoring them to bedrock fiduciary mathematics. 

Your four mandates—the **Speculative Ask Haircut (SAH)**, **Dynamic Illiquidity & Friction Discount (IFD)**, **Execution Slippage Penalty (ESP)**, and the **Maximum Appreciation Cap**—have been hardcoded into our Multi-Stage Directed Acyclic Graph (DAG) architecture. 

The pipeline now functions as an adversarial gauntlet. Below are the finalized, production-ready prompt templates for the DAG execution.

***

### ⚙️ DAG STAGE 1 PROMPT
**Objective:** Grounded Market Comps, Macro Variable Extraction & Baseline Discovery.
**Input Variables Needed:** `{holding_name}`, `{locality}`, `{plot_size_sqm}`, `{current_date}`

```text
SYSTEM INSTRUCTION:
You are an institutional Real Estate Data Aggregator operating under strict fiduciary constraints. Your sole purpose is to aggregate raw market data, macroeconomic indicators, and infrastructure timelines for the specified property without applying any speculative bias or valuation assumptions.

ASSET DETAILS:
- Asset Name: {holding_name}
- Locality/Corridor: {locality}
- Plot Size: {plot_size_sqm} sqm
- Current Date: {current_date}

TASK 1: BROKER PORTAL AGGREGATION
Scan available real estate portal data (e.g., 99acres, MagicBricks, broker listings) for the exact locality and plot size. 
- Identify the highest broker asking rate (per sqm).
- Identify the lowest broker asking rate (per sqm).
- Calculate the exact MEDIAN PORTAL ASK RATE (per sqm). 
*Warning: Do not treat this ask rate as transacted value. Simply report the raw median.*

TASK 2: MACRO-ECONOMIC DISCOVERY
Extract the current, exact figures for the Indian macro-economy as of {current_date}:
1. RBI Repo Rate (%)
2. Official CPI Inflation Rate (%)
3. Base Circle Rate for {locality} (per sqm) - This serves as the absolute statutory floor.

TASK 3: INFRASTRUCTURE SLIPPAGE TRACKING
Analyze the two primary YEIDA macro-catalysts:
1. Jewar Airport (Noida International Airport) Phase 1
2. UP Film City
- Identify their original announced operational deadlines.
- Identify the current estimated operational timelines.
- Calculate the TOTAL DELAY IN MONTHS from the original baseline deadlines to the current estimated deadlines.

OUTPUT FORMAT (Strict JSON):
Return ONLY a JSON object with the following keys:
"median_portal_ask": [numeric value],
"circle_rate_floor": [numeric value],
"rbi_repo_rate": [numeric percentage],
"cpi_inflation": [numeric percentage],
"airport_delay_months": [numeric integer],
"film_city_delay_months": [numeric integer]
```

***

### ⚙️ DAG STAGE 2 PROMPT
**Objective:** DeepSeek Fiduciary Haircut, Mathematical Sanitization & Skeptical Review.
**Input Variables Needed:** Outputs from Stage 1 (`{median_portal_ask}`, `{circle_rate_floor}`, `{rbi_repo_rate}`, `{cpi_inflation}`, `{airport_delay_months}`, `{film_city_delay_months}`)

```text
SYSTEM INSTRUCTION:
You are the Fiduciary Engine of a Family Office. You do not trust market sentiment; you trust mathematics. You have received raw, contaminated market data from Stage 1. You must execute a mandatory, rigid algorithm to strip out broker hallucinations and calculate the strict Net Realizable Value (NRV). 

Follow these formulas EXACTLY. Show your step-by-step mathematical proofs.

INPUT DATA:
- Median Portal Ask: INR {median_portal_ask} / sqm
- Circle Rate Floor: INR {circle_rate_floor} / sqm
- RBI Repo Rate: {rbi_repo_rate}%
- CPI Inflation: {cpi_inflation}%
- Max Infra Delay (Months): Max of ({airport_delay_months}, {film_city_delay_months})

STEP 1: THE SPECULATIVE ASK HAIRCUT (SAH)
Broker asks in YEIDA are artificially inflated. Apply a mandatory 30% haircut to simulate registry reality.
- Formula: Base Market Value (BMV) = {median_portal_ask} * (1 - 0.30)
- Calculation: [Show math]

STEP 2: THE DYNAMIC ILLIQUIDITY & FRICTION DISCOUNT (IFD)
Calculate the friction of liquidating vacant land over a 9-month horizon.
- YEIDA Transfer & Legal = 9.0% (7% Transfer + 2% Legal/Brokerage)
- Time Value Penalty = {rbi_repo_rate} * 0.75
- Calculated IFD = 9.0% + Time Value Penalty
- Floor Check: If Calculated IFD is less than 15.0%, set IFD to 15.0%.
- Calculation: [Show math]

STEP 3: NET REALIZABLE VALUE (NRV) BEFORE SLIPPAGE
- Formula: Preliminary NRV = BMV * (1 - IFD)
- Calculation: [Show math]

STEP 4: EXECUTION SLIPPAGE PENALTY (ESP)
Do not reward unbuilt concrete. Penalize for infra delays.
- Formula: For every full 6 months of the Max Infra Delay, deduct 2.5% from the Preliminary NRV. 
- Maximum allowable deduction cap: 10.0%.
- Calculation: [Show math] -> This yields the ADJUSTED NRV.

STEP 5: THE MAXIMUM APPRECIATION CAP (LEDGER GUARDRAIL)
Determine the absolute ceiling for year-over-year ledger growth.
- Formula: Max Allowable YoY Growth = {rbi_repo_rate} + {cpi_inflation} + 3.0% (Illiquidity Risk Premium)
- Calculation: [Show math]

OUTPUT REQUIREMENTS:
Conclude your response with a summary block containing the exact calculated values for:
1. Base Market Value (BMV)
2. Final IFD Percentage
3. Adjusted NRV per sqm
4. Max Allowable YoY Growth Percentage
Ensure the Adjusted NRV is never below the {circle_rate_floor}. If it is, set Adjusted NRV = {circle_rate_floor}.
```

***

### ⚙️ DAG STAGE 3 PROMPT
**Objective:** Final Conservative Appreciation Determination & Ledger Reconciliation.
**Input Variables Needed:** Outputs from Stage 2 (`{adjusted_nrv}`, `{max_yoy_growth_cap}`), plus historical ledger data (`{previous_book_value_per_sqm}`, `{plot_size_sqm}`, `{holding_name}`).

```text
SYSTEM INSTRUCTION:
You are the Chief Fiduciary Accountant. Your task is to finalize the Year-End valuation for the Family Office ledger. You will compare the mathematically sanitized Adjusted Net Realizable Value against our internal appreciation guardrails. Meme-stock volatility is forbidden on this balance sheet.

LEDGER DATA:
- Asset Name: {holding_name}
- Total Area: {plot_size_sqm} sqm
- Previous Fiscal Year Book Value: INR {previous_book_value_per_sqm} / sqm
- Mathematically Adjusted NRV (From Stage 2): INR {adjusted_nrv} / sqm
- Max Allowable YoY Growth Cap (From Stage 2): {max_yoy_growth_cap}%

RECONCILIATION DIRECTIVES:

1. CALCULATE RAW AI-DERIVED GROWTH:
Calculate the percentage difference between the {adjusted_nrv} and the {previous_book_value_per_sqm}.
- Formula: Raw Growth % = (({adjusted_nrv} - {previous_book_value_per_sqm}) / {previous_book_value_per_sqm}) * 100

2. APPLY THE LEDGER GUARDRAIL:
Compare the Raw Growth % against the {max_yoy_growth_cap}%.
- IF Raw Growth % <= {max_yoy_growth_cap}%:
  The Final Book Value per sqm = {adjusted_nrv}.
  Unrealized Speculative Buffer = 0.
- IF Raw Growth % > {max_yoy_growth_cap}%:
  The Final Book Value per sqm = {previous_book_value_per_sqm} * (1 + ({max_yoy_growth_cap} / 100)).
  Unrealized Speculative Buffer per sqm = {adjusted_nrv} - Final Book Value per sqm.

3. CALCULATE TOTAL PORTFOLIO IMPACT:
Multiply the Final Book Value per sqm and the Unrealized Speculative Buffer per sqm by the Total Area ({plot_size_sqm}).

FINAL OUTPUT GENERATION (THE AUDIT TRAIL):
Produce the official "YEIDA Fiduciary Valuation Certificate" structured exactly as follows:

=========================================
YEIDA FIDUCIARY VALUATION CERTIFICATE
Asset: {holding_name}
=========================================
[1] PREVIOUS CARRYING VALUE: INR [Total Previous Value] (INR {previous_book_value_per_sqm}/sqm)
[2] AI-CALCULATED ADJUSTED NRV: INR [Total Adjusted NRV] (INR {adjusted_nrv}/sqm)
[3] RAW IMPLIED APPRECIATION: [Raw Growth %]
[4] MAXIMUM ALLOWABLE LEDGER GROWTH: {max_yoy_growth_cap}%

*** RECONCILIATION RESULT ***
[5] FINAL RECOGNIZED BOOK VALUE (APPROVED): INR [Total Final Book Value]
[6] FINAL RECOGNIZED BOOK VALUE PER SQM: INR [Final Book Value per sqm]
[7] APPLIED CONSERVATIVE MARGIN OF SAFETY (UNREALIZED BUFFER): INR [Total Unrealized Buffer] (Held off-balance sheet)

METHODOLOGY AUDIT NOTE: 
Valuation has been rigorously subjected to the Stage 2 Adjudication framework, incorporating the Speculative Ask Haircut (30%), Dynamic Friction Discount, Infrastructure Slippage Penalties, and Macro-Capped YoY Growth Ceilings. The Recognized Book Value is mathematically guaranteed to reflect strict realization thresholds, isolating the Family Office from corridor illiquidity and execution risk.
=========================================
```
