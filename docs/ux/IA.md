# Vault — Page-Level Information Architecture (`docs/ux/IA.md`)

> **Mandate for `@ui-1` (`portfolio`), `@ui-2` (`expenses` + `tracker`), and `@ui-3` (`jewellery` + `public` + `admin`):**
> The user rejected two earlier passes that only changed colors, tokens, and surface polish. Every page MUST undergo a **structural page-level redesign** — rethinking what content leads, how sections are grouped into workbenches, what is primary vs. secondary, and what moves behind progressive disclosure (drawers, tabs, or collapsible folios).
>
> **Hard Invariants:** Preserve 100% of Django template blocks (`title`, `extra_head`, `page_header`, `content`, `login_content`, `chart_js`, `extra_js`), URL names, context variables, CSRF tokens, form field names, `<dialog>` modal IDs, and JS hooks (`openModal`, `closeModal`, `confirmDelete`, `initPagination`, Chart.js canvas IDs).

---

## Global Structural Rules (Every Page)

1. **No Card Soup / No Nested Cards**:
   - Never put `.stat-card` boxes inside a `.card.hero-gradient`.
   - Every dashboard or detail route opens with a **Full-Width Ledger Summary Band (`.v-ledger-band`)** or **Ruled Stat Strip (`.v-stat-strip`)** where cells share `1px` structural hairlines (`rgba(226, 232, 240, 0.08)`).
2. **The Signature Horizon Bar (`.v-horizon`)**:
   - Every primary route includes a proportional multi-segment horizontal bar (`.v-horizon` + `.v-horizon-legend`) inside its top `.v-ledger-band` to visualize allocation share, spend pace, FY goal progress, or custody split in the first viewport before scrolling.
3. **Asymmetric Workbenches (`.v-workbench`) over Endless Vertical Stacking**:
   - Instead of stacking 6–10 full-width cards vertically down the page, organize the primary workspace into a purposeful **Asymmetric Workbench** (`8 cols` primary ledger/feed + `4 cols` sticky analytical/context rail on `lg+`) or a **Segmented Folio**.
4. **No Eyebrow Kickers**:
   - Never place tiny uppercase kicker labels above `<h1>`, `<h2>`, or `<h3>` headings. Headings stand on their own weight (`1.5rem` page title, `1rem` panel title) paired with an inline count pill or subtitle below.
5. **Action Hierarchy**:
   - Each page header has at most **ONE primary filled button** (`.btn-primary`). Secondary utilities (Sync Sheets, Refresh Prices, AI Insights, Year View, Statements, Settings) sit in a compact `.v-toolbar` or overflow menu.

---

## Slice 1: `@ui-1` — Portfolio (`templates/portfolio/`)

### 1. `portfolio/master.html` & `portfolio/baby.html` (Master & Child Portfolio Folio)
- **Job**: Give the `PRIMARY` controller an immediate, institutional-grade consolidated statement of household net worth, asset allocation, FY capital vs. market gains, goal funding progress, and per-asset-class holdings.
- **Page Header (`{% block page_header %}`)**:
  - Left: Segmented switcher pill (`.v-segmented`) toggling between **Master Portfolio** and **Child Portfolio** right beside the page title, plus subtitle.
  - Right: `.v-toolbar` grouping `Sync Sheets`, `Refresh Prices`, `AI Insights`, and `Biometrics` as quiet secondary toolbar buttons (`.v-btn-secondary`), with `Growth` (or `Select Holdings` on `baby.html`) as the primary CTA.
- **First Viewport — Lead (`.v-ledger-band`)**:
  - **Left Lead Cell (5 cols)**: Total Portfolio Value (`{{ total_value|inr }}`) in Display Figure (`2.25rem` `tabular-nums`), inline net return delta badge (`.v-delta-pos` / `.v-delta-neg` with `{{ total_returns|inr }}` and `{{ return_pct }}%`), the "Include Real Estate" toggle inline in the header row, and the **Signature Horizon Bar (`.v-horizon`)** showing proportional asset-class weights across Equity, Debt/EPF, Gold/Commodities, Real Estate, and Cash.
  - **Right Hairline Grid (7 cols, 4 `.v-stat-cell` cells)**:
    1. *Invested Capital* (`{{ total_invested|inr }}`)
    2. *Total Returns* (`{{ total_returns|inr }}` + `{{ return_pct }}%`)
    3. *FY Performance* (`{{ fy_performance.total_change|inr }}` split into `Added` vs `Market`)
    4. *Goal Spotlight / Liquid Share* (`{{ goal_roadmap.spotlight }}` or asset count)
- **Primary vs. Secondary Grouping**:
  - **Sticky Folio Navigation Rail (`.section-nav`)**: Clean horizontal pill bar jumping to asset groups (`#overview`, `#equities`, `#retirement`, `#fixed-income`, `#real-assets`, `#goals`).
  - **Overview Workbench (Asymmetric 2-Column Split on `lg+`)**:
    - *Left (7 cols)*: **Asset Class Matrix & Allocation Breakdown** (`#allocationChart` + `#consolidatedChart` side-by-side with a ruled allocation table showing Invested, Current, P&L, and Weight % in one scannable view — open by default, never hidden in a collapsed box).
    - *Right (5 cols)*: **AI Portfolio Intelligence & Risk Brief** (`ai_insight` panel). Lead with the AI Score Ring + executive summary + top 2 critical/warning action items; tuck the full multi-stage category audit and tax/rebalancing details inside a clean `<details class="v-disclosure">` or modal drawer so it doesn't push holdings 1,000px down the page.
  - **Asset Class Ledger Sections (`#equities`, `#retirement`, `#fixed-income`, `#real-assets`)**:
    - Group the 11 asset classes into 4 logical domain folios instead of 11 undifferentiated cards:
      1. **Equities & Market Securities**: Indian Stocks & Mutual Funds (Zerodha accounts summary + member chips), US RSUs.
      2. **Retirement & Sovereign Long-Term**: EPF, PPF (`pf`), NPS.
      3. **Fixed Income & Liquidity**: Fixed Deposits (`fd`), Bonds, Cash & Bank Balances.
      4. **Real Assets & Alternatives**: Physical Gold/Silver (`commodities`), Real Estate (`real_estate`), Crypto (`crypto`).
    - Each asset section uses `.v-panel` with `.v-panel-header` (title + total value + P&L pill + `Manage / Detail` link + `+ Add` button) and a clean `.v-table` on desktop / `.v-mobile-row` list on mobile.
  - **Goals Section (`_goals_section.html`)**: Rendered as a structured **Goal Funding Matrix** where each goal shows target amount, current funded value, a `.v-horizon` progress bar, and linked instrument pills, with edit/add actions opening their existing modals.
  - **Modals (`_bond_form_modal.html`, `_cash_form_modal.html`, `_commodity_form_modal.html`, `_crypto_form_modal.html`, `_epf_form_modal.html`, `_fd_form_modal.html`, `_nps_form_modal.html`, `_pf_form_modal.html`, `_real_estate_form_modal.html`)**: Restyle every modal with `.v-modal-box`, structured 2-column `.v-form-grid` for numeric/date pairs, and sticky `.v-modal-footer`.

### 2. `portfolio/growth.html` (Capital Inflow vs. Market Compounding Ledger)
- **Job**: Separate fresh savings added from market returns across months and financial years.
- **Lead**: Page Header with FY switcher tabs (`.fy-tabs`) + Monthly/Yearly segmented view toggle (`#btnMonthly`, `#btnYearly`).
- **Structure**:
  - Top `.v-stat-strip` summarizing FY Total Added, FY Market Returns, Opening Value, and Closing Value.
  - Side-by-side Chart Workbench (`#growthBar` stacked bar + `#valueChart` trajectory line in `.v-panel` containers).
  - Below: Ruled Monthly/Yearly Ledger Table with pinned Month/Year column, Opening Balance, Money Added, Market Return, Return %, and Closing Balance (`tabular-nums`).

### 3. `portfolio/zerodha_consolidated.html` & `portfolio/zerodha_detail.html` (Equity & Mutual Fund Blotter)
- **Job**: Deep-dive into household or individual Zerodha demat holdings (Stocks, ETFs, Mutual Funds, SGBs).
- **Lead**: `.v-ledger-band` with Total Equity Value, Net P&L + %, Day/XIRR metric cells, and `.v-horizon` bar showing Stocks vs. Mutual Funds vs. ETFs/Gold split.
- **Workbench**:
  - Top filter/search bar + account switcher pills + `#equityAllocationChart` compact side panel.
  - Full-width sortable Blotter Table (`.v-table`) with crisp right-aligned columns (Instrument, Qty, Avg Cost, LTP, Invested, Current, Net P&L, Weight %). Preserve all `data-sort` hooks and breakdown modals.

### 4. Asset Detail Pages (`epf_detail.html`, `nps_detail.html`, `pf_detail.html`, `fd_detail.html`, `bonds_detail.html`, `cash_detail.html`, `commodities_detail.html`, `crypto_detail.html`, `real_estate_detail.html`)
- **Job**: Focused ledger and audit trail for a single asset class.
- **Lead**: Unified `.v-ledger-band` at the top of every detail page showing Current Valuation, Invested Capital, Total Return / Yield, and a proportional `.v-horizon` breakdown (e.g., Employee vs. Employer share + Interest on EPF; Tier I vs. Tier II or scheme mix on NPS; Bank split on FD/Cash; Property appreciation + AI Land Appraisal status on Real Estate).
- **Primary vs. Secondary**:
  - Primary: The holdings/passbook ledger table in a `.v-panel` with inline edit/delete triggers.
  - Secondary / Disclosure: On `real_estate_detail.html`, present the AI Land Appraisal report as an executive valuation certificate with collapsible methodology/comparable sales sections. On `epf_detail.html` / `nps_detail.html` / `fd_detail.html`, group passbook/tranche history cleanly with filter/sort controls.

### 5. `portfolio/unlock.html` (Vault Security Gate)
- **Job**: Authenticate into the 30-minute protected portfolio/jewellery session via portfolio password or WebAuthn passkey.
- **Structure**: Centered, high-craft **Fiduciary Security Gate** card (`max-w-md`) on the Folio Ground: crisp Vault emblem, clear explanation of the 30-minute session lock, primary Passkey / Biometric unlock button (when supported/configured), and password input with instant focus.

---

## Slice 2: `@ui-2` — Cashflow, Expenses & Tracker (`templates/expenses/`, `templates/tracker/`)

### 1. `expenses/home.html` & `expenses/_expense_modal.html` (Monthly Cashflow & Spend Triage Workbench)
- **Job**: Daily/weekly command center to monitor current month spend pace against last month, triage unlinked refunds or flagged anomalies, inspect category burn, and log/edit transactions.
- **Page Header**:
  - Left: Title `Expenses` + inline Month Switcher pill (`.exp-month-switch` with `prev_month`, `summary.label`, `next_month`, and `This month` reset button).
  - Right: `.v-toolbar` with explicit labeled/icon buttons for `Year View`, `Statements`, `Settings`, and primary `+ Add Expense` CTA (`Expenses.open()`).
- **First Viewport — Lead (`.v-ledger-band`)**:
  - **Left Lead Cell (5 cols)**: Net Spend (`{{ summary.total|inr }}`) in Display Figure, pace delta badge vs. same day last month (`{{ pace.gap|inr_short }} more/less vs Day {{ pace.day }}`), refunded credit pill if any, and **Signature Horizon Bar (`.v-horizon`)** encoding top category share of spend.
  - **Right Hairline Cells (7 cols)**:
    - Cumulative Pace Chart (`#paceChart`, 110px height) comparing this month's daily burn curve against last month's dashed contour line, flanked by 3 ruled `.v-stat-cell` metrics: *Transactions* (`{{ summary.count }}`), *Active EMIs* (`{{ summary.emi_summary.monthly_commitment|inr_short }}/mo`), and *Projected / Daily Avg* (`{{ pace.projected|inr_short }}`).
- **Primary Workbench (Asymmetric 2-Column Layout on `lg+`: 8 cols Feed + 4 cols Intelligence Rail)**:
  - **Left Primary Column (8 cols)**:
    - **Needs Attention / Triage Strip** (if anomalies, unreviewed Gmail imports, or unlinked refunds exist): Compact, high-priority `.v-panel` at the top of the feed with `.exp-attn` rows.
    - **Filter & Search Bar**: Sticky search input, source/category filter pills, and sort controls.
    - **Day-Grouped Transaction Ledger**: Sticky `.exp-day-header` bars with daily subtotal (`tabular-nums`) and crisp transaction rows showing category icon badge, merchant/description, payment source pill, refund/EMI tags, and right-aligned rupee amount.
  - **Right Sticky Rail (4 cols)**:
    - **Category Burn Breakdown**: Ranked `.exp-cat-row` list with proportional `.exp-bar` bars, share %, and amount (clicking filters the feed).
    - **Spend Highlights & Pulse Chips**: Top merchant, biggest single spend, and rising category callouts arranged as a ruled `.v-divide-list` inside a single `.v-panel` (instead of scattered horizontal chips).
    - **Active EMI Commitments** (progressive disclosure `<details>` or compact panel when EMIs exist).
- **Expense Modal (`_expense_modal.html`, `_category_fields.html`, `_source_fields.html`)**:
  - Restyle as a clean ledger entry dialog with prominent `exp-amount-input` at top, segmented type selector (Expense / Refund / Transfer), and 2-column field layout. Preserve all IDs and JS bindings in `expenses.js`.

### 2. `expenses/statements.html` & `expenses/statement_detail.html` (Credit Card Statement Reconciliation Center)
- **Job**: Track monthly credit card PDF statements, bill due dates, total dues, and 3-stage transaction reconciliation (Matched vs. Missing vs. Discrepancy).
- **`statements.html` Structure**:
  - Top `.v-ledger-band` showing Total Statement Dues, Statements Reconciled count, Upcoming Due Dates, and Gmail PDF Sync trigger.
  - Card-by-card Statement Matrix (`.v-panel` table + mobile rows) showing Card Name, Statement Period, Total Due, Min Due, Due Date, Reconciliation Status badge, and `Inspect` action.
- **`statement_detail.html` Structure**:
  - Top `.v-ledger-band` with Card Title, Billing Cycle, Total Amount Due, Payment Due Date, and a **3-Segment Reconciliation Horizon Bar** (Matched Alerts % vs. Imported from PDF % vs. Unmatched/Pending %).
  - **3-Stage Reconciliation Workbench**: Tabbed or clearly sectioned ledger tables separating (1) *Unmatched / Needs Action Lines*, (2) *Reconciled & Matched Transactions*, and (3) *Active EMIs & Fee Breakdown* from the PDF.

### 3. `expenses/year.html` (Indian FY Annual Spend Matrix)
- **Job**: Macro analysis of household spending across all 12 months of the April–March Financial Year.
- **Structure**:
  - Page Header with `.fy-tabs` switcher.
  - Top `.v-ledger-band` with FY Total Spend, Monthly Average, Highest Spend Month, and YoY / Category Horizon Bar.
  - Primary Workbench: Category × Month cross-tabulation / trend matrix with inline `.exp-spark` 12-month bars, category share, and monthly totals.

### 4. `expenses/settings.html` (Ingestion, Cards, Categories & Rules Control Panel)
- **Job**: Configure Gmail OAuth 2.0 sync, credit card PDF unlock passwords/last-4 digits, custom categories, and merchant auto-categorization rules.
- **Structure**: Replace stacked miscellaneous cards with a **2-Column Settings Workbench** (left vertical section nav or clean top tabs on mobile; right focused configuration panels for *Gmail Sync Status*, *Credit Cards & PDF Passwords*, and *Categories & Rules*).

### 5. `tracker/dashboard.html` (Indian FY Monthly Savings & Goal Pacing Ledger)
- **Job**: Track April–March monthly savings, extra income, and transfers against annual and monthly savings goals.
- **Page Header**: FY Title (`{{ fy_label }}`) + date range subtitle on left; `.fy-tabs` switcher + `Manage Goals` (`.v-btn-secondary`) + primary `+ Add Entry` (`newTransaction()`) on right.
- **First Viewport — Lead (`.v-ledger-band`)**:
  - **Left Lead Cell (5 cols)**: Annual Savings Goal (`{{ total_goal|inr }}`) and Achieved (`{{ goal_achieved|inr }}`, `{{ goal_pct }}%`), pace status badge (`{{ pace.gap_abs|inr_short }} ahead/behind pace`), and **Signature Horizon Bar (`.v-horizon`)** showing Achieved vs. Remaining (or Surplus).
  - **Right Hairline Grid (7 cols, 4 `.v-stat-cell` cells)**:
    1. *Net Savings* (`{{ total_savings|inr }}`)
    2. *Extra Income* (`{{ total_income|inr }}`)
    3. *Transfers* (`{{ total_transfers|inr }}`)
    4. *HRA Balance* (`{{ hra_balance|inr }}` linking to `hra_tracker`)
- **Primary Workbench**:
  - **12-Month FY Pacing Matrix (`monthly_data`)**: A cohesive 12-cell ruled fiscal calendar grid (Apr → Mar) where each month cell shows Month code, Saved amount, Surplus/Deficit vs. goal, compact progress bar, and inline note indicator.
  - **Asymmetric Analytical Split (2 columns on `lg+`)**:
    - *Left (6 cols)*: Monthly Savings vs. Goal Bar Chart (`#barChart`).
    - *Right (6 cols)*: Cumulative Trajectory Line Chart (`#lineChart`).
  - **Transactions & Goal Increments Ledger**: Full-width `.v-panel` table of FY entries with category/type filters, pagination (`initPagination`), and inline edit/delete hooks.

### 6. `tracker/hra.html` (HRA Rent & Tax Exemption Ledger)
- **Job**: Shared ledger for `PRIMARY`, `ACCOUNT_HOLDER`, and `LANDLORD` to verify monthly rent transfers, HRA inflows, and net rent balance.
- **Structure**:
  - Top `.v-ledger-band` with Net HRA Balance, Total Rent Paid, Total HRA Transferred, and Landlord details.
  - Clean chronological Rent & Transfer Ledger Table with receipt/verification badges and quick entry modal.

### 7. `tracker/notes.html` (Household Financial Notes & Checklists)
- **Job**: Collaborative scratchpad for tax tasks, renewal reminders, and household financial checklists.
- **Structure**: Clean 2-pane or masonry workspace with pinned/active checklists leading and completed/archived notes tucked below, using crisp `.v-panel` note sheets without decorative clutter.

### 8. `tracker/login.html` (Vault Sign-In Portal)
- **Job**: Authenticate household members via Google OAuth or credentials.
- **Structure**: Authoritative **Private Bank Vault Portal** layout — split desktop presentation (left brand thesis & security architecture summary; right crisp authentication card on `#111722` Ledger Sheet) collapsing cleanly to a focused single card on mobile.

---

## Slice 3: `@ui-3` — Jewellery Vault, Public & Admin (`templates/jewellery/`, `templates/public/`, `templates/admin/`)

### 1. `jewellery/dashboard.html` (Precious Metals & Ornament Custody Ledger)
- **Job**: Catalogue family gold, silver, platinum, and diamond ornaments across `BANK_LOCKER` and `HOME_SAFE` with live purity-adjusted valuation.
- **Page Header**:
  - Left: Title `Jewellery Vault` + live Bullion Ticker Pills (`24K Gold: {{ gold_rate|inr }}/g`, `Silver: {{ silver_rate|inr }}/g`, `Updated {{ rates_as_of|timesince }} ago`).
  - Right: Back to Portfolio link + primary `+ Add Item` button (`openAddJewelleryModal()`).
- **First Viewport — Lead (`.v-ledger-band`, shown when `is_primary`)**:
  - **Left Lead Cell (5 cols)**: Estimated Collection Value (`{{ total_estimated_value|inr }}`), purity valuation note, and **Signature Custody Horizon Bar (`.v-horizon`)** showing proportional value split between **Bank Locker** vs. **Home Safe** (`value_by_location`).
  - **Right Hairline Grid (7 cols, 3 `.v-stat-cell` cells)**:
    1. *Gold Holdings* (`{{ total_weight_gold|floatformat:2 }}g` in Bullion Gold ink)
    2. *Silver Holdings* (`{{ total_weight_silver|floatformat:2 }}g` in Bullion Silver ink)
    3. *Vault Inventory* (`{{ items|length }}` items)
- **Unified Filter & Custody Toolbar**:
  - Single horizontal control bar combining Custody Location pills (`All`, `Bank Locker`, `Home Safe`), live search input (`#filter_search` + `#search_results`), and Metal / Category dropdown filters (`#filterForm`) without stacking three separate filter boxes.
- **Collection Gallery & Ledger**:
  - High-density catalog grid on desktop + compact `.v-mobile-row` list on mobile, each item displaying WebP thumbnail (or `.jw-type-tile`), purity badge (`24K`/`22K`/`18K`), custody badge (`BANK_LOCKER`/`HOME_SAFE`), net weight in grams (`tabular-nums`), and live estimated value (`tabular-nums`).

### 2. `jewellery/detail.html` (Ornament Assay & Custody Dossier)
- **Job**: Inspect and edit a single ornament's photos, gross/net weight, fineness, custody location, and valuation breakdown.
- **Structure**:
  - Page Header with breadcrumb back to Jewellery Vault, item title, custody & metal badges, and `Edit` / `Delete` actions.
  - **2-Column Assay Dossier (`#viewModeContainer`)**:
    - *Left (5 cols)*: High-resolution photo frame with thumbnail strip / upload control.
    - *Right (7 cols)*: Ruled Assay Certificate panel (`.v-panel`) displaying Live Valuation, Metal & Purity, Gross vs. Net Weight (`g`), Custody Location, Acquisition Notes, and Valuation Math formula.
  - Preserve `#editModeContainer` inline form toggle and all JS hooks in `jewellery.js`.

### 3. `public/base.html`, `public/about.html`, `public/privacy.html`, `public/terms.html` (Public & Legal Folio)
- **Job**: Present Vault's private household identity, Google OAuth verification disclosures, privacy commitments, and terms of service.
- **Structure**:
  - Replace all emoji icons (`📈`, `💳`, `🧾`, `🏠`, `🔑`, `✉️`, `🛡️`) in `about.html` with crisp inline SVG icons.
  - Redesign `public/base.html` and `static/css/public.css` (or inline/shared classes) to match the **Private Bank Folio** identity: obsidian slate ground (`#0b0f17`), crisp hairline-ruled feature matrix on `about.html`, and clean `68ch` editorial measure with sticky table-of-contents / section anchors on `privacy.html` and `terms.html`.
  - Keep `#nav-signin`, `#hero-signin`, `#hero-privacy`, and all URL tags intact.

### 4. `admin/base_site.html` (Django Admin Theme Integration)
- **Job**: Harmonize Django Admin with the Vault dark ledger palette (`#0b0f17` ground, `#111722` sheets, `#6366f1` indigo accents, `Inter` tabular typography) while keeping all standard Django admin controls functional.
