# Vault — Page-Level Information Architecture (`docs/ux/IA.md`)

Authoritative route-by-route Information Architecture specification for the **Vault Family Office & Private Ledger System**.

**Template & Hook Invariants**: Every route preserves its Django template blocks (`title`, `extra_head`, `page_header`, `content`, `login_content`, `chart_js`, `extra_js`), URL names, context variables, CSRF tokens, form field names, `<dialog>` modal IDs, and JS hooks (`openModal`, `closeModal`, `confirmDelete`, `initPagination`, Chart.js canvas IDs).

---

## Global Structural Rules

1. **Ruled Ledger Bands over Card Soup**:
   - Primary dashboards and detail routes open with a **Full-Width Ledger Summary Band (`.v-ledger-band`)** or **Ruled Stat Strip (`.v-stat-strip`)** divided by `1px` structural hairlines (`var(--v-hairline-subtle)`).
   - Bordered cards never nest inside `.v-panel` or `.v-ledger-band`; internal sections use flush `1px` hairline dividers.
2. **Signature Horizon Bar (`.v-horizon`)**:
   - Primary routes display a proportional multi-segment horizontal bar (`.v-horizon` + `.v-horizon-legend`) inside `.v-ledger-band` to encode allocation share, spend pace, FY goal progress, or custody split above the fold.
3. **Balanced Workbenches (`.v-workbench`)**:
   - Primary content organizes into balanced 2-column workbenches (`8/4`, `7/5`, or `1/1` on `lg+` with `align-items: start`) or segmented folios (`.v-segmented`), avoiding empty column voids and endless vertical card stacks.
4. **No Eyebrow Kickers**:
   - Headings (`1.5rem` page title, `1rem` panel title) carry their own hierarchy paired with inline count badges or concise subtitles — never tiny uppercase eyebrow kickers above `<h1>`, `<h2>`, or `<h3>`.
5. **Single Primary Action**:
   - Each `.v-page-header` features at most one primary button (`.v-btn-primary`); secondary actions (`Sync Sheets`, `Refresh Prices`, `AI Insights`, `Year View`, `Statements`, `Settings`) group into `.v-toolbar`.

---

## 1. Portfolio & Wealth Routes (`templates/portfolio/`)

### 1.1 `portfolio/master.html` & `portfolio/baby.html` (Master & Child Portfolio Folio)
- **Header**: Segmented switcher (`.v-segmented`) toggling **Master Portfolio** and **Child Portfolio** beside the page title; `.v-toolbar` grouping `Sync Sheets`, `Refresh Prices`, `AI Insights`, and `Biometrics` alongside the primary CTA (`Growth` on `master.html`, `Select Holdings` on `baby.html`).
- **Ledger Summary Band (`.v-ledger-band`)**:
  - **Left Lead Cell (`5` cols)**: Total Portfolio Value (`{{ total_value|inr }}` in Display Figure `tabular-nums`), net return delta badge (`.v-delta-pos` / `.v-delta-neg`), inline Real Estate inclusion toggle, and `.v-horizon` asset-class bar.
  - **Right Hairline Grid (`7` cols, 4 `.v-stat-cell` cells)**: *Invested Capital*, *Total Returns*, *FY Performance* (`Added` vs. `Market`), and *Goal Spotlight / Liquid Share*.
- **Folio Navigation & Overview**:
  - Sticky `.section-nav` rail jumping across `#overview`, `#equities`, `#retirement`, `#fixed-income`, `#real-assets`, and `#goals`.
  - `#overview` pairs the Allocation & Consolidation Charts + ruled allocation table with the AI Portfolio Intelligence panel (score ring, executive summary, flush hairline-divided findings, and collapsible disclosures without creating empty column voids when collapsed).
- **4 Domain Asset Folios**:
  1. **Equities & Market Securities**: Indian Stocks & Mutual Funds (Zerodha accounts + member chips) and US RSUs.
  2. **Retirement & Sovereign Long-Term**: EPF, PPF (`pf`), and NPS.
  3. **Fixed Income & Liquidity**: Fixed Deposits (`fd`), Bonds, and Cash & Bank Balances.
  4. **Real Assets & Alternatives**: Physical Gold/Silver (`commodities`), Real Estate (`real_estate`), and Crypto (`crypto`).
- **Goals Matrix (`_goals_section.html`)**: Full-width 2-column Active FY Goal band (left: target, ex-RE formula, `.v-horizon` progress bar, pace status & hairline note; right: flush 4-cell `.v-stat-grid`), paired with Upcoming FY Roadmaps and Closed FY Track Record (`Unrecorded` / `No Snapshot` when `closed_value` is absent; `Achieved` strictly when recorded closing value meets target).
- **Holding Modals (`_*_form_modal.html`)**: Native `<dialog>` sheets using `.v-modal-box`, 2-column `.v-form-grid` numeric/date pairs, and sticky `.v-modal-footer`.

### 1.2 `portfolio/growth.html` (Capital Inflow vs. Market Compounding Ledger)
- **Header**: `.fy-tabs` switcher + Monthly/Yearly `.v-segmented` view toggle (`#btnMonthly`, `#btnYearly`).
- **Workspace**: Top `.v-stat-strip` (FY Total Added, FY Market Returns, Opening Value, Closing Value), side-by-side chart workbench (`#growthBar` + `#valueChart`), and ruled ledger table with pinned Month/Year column (`tabular-nums`).

### 1.3 `portfolio/zerodha_consolidated.html` & `portfolio/zerodha_detail.html` (Equity & Mutual Fund Blotter)
- **Lead**: `.v-ledger-band` with Total Equity Value, Net P&L + %, XIRR/account cells, and Stocks vs. Mutual Funds vs. ETFs/Gold `.v-horizon` split.
- **Workbench**: Search/filter toolbar + account switcher pills + `#equityAllocationChart` panel and full-width sortable `.v-table` blotter (`data-sort` hooks preserved).

### 1.4 Asset Detail Pages (`epf_detail.html`, `nps_detail.html`, `pf_detail.html`, `fd_detail.html`, `bonds_detail.html`, `cash_detail.html`, `commodities_detail.html`, `crypto_detail.html`, `real_estate_detail.html`)
- **Lead**: `.v-ledger-band` displaying Current Valuation, Invested Capital, Total Return / Yield, and asset-specific `.v-horizon` split.
- **Workbench**: Primary holdings/passbook `.v-table` + `.v-mobile-row` ledger with inline edit/delete controls; `real_estate_detail.html` presents the 3-stage AI Land Appraisal certificate with collapsible methodology and comparable disclosures.

### 1.5 `portfolio/unlock.html` (Vault Security Gate)
- Centered narrow Fiduciary Security Gate panel (`max-w-[420px] mx-auto`) displaying the Vault emblem, 30-minute session notice, WebAuthn passkey unlock button, and password field with an inline trailing visibility toggle inside the input box.

---

## 2. Cashflow, Expenses & Savings Routes (`templates/expenses/`, `templates/tracker/`)

### 2.1 `expenses/home.html` & `expenses/_expense_modal.html` (Monthly Cashflow & Spend Triage Workbench)
- **Header**: `Expenses` title + `.exp-month-switch` pill on left; `.v-toolbar` (`Year View`, `Statements`, `Settings`, primary `+ Add Expense`) on right.
- **Ledger Summary Band**: Net Spend Display Figure, pace delta vs. same day prior month, refunded credit pill, and top-category `.v-horizon` bar on left (`5` cols); cumulative `#paceChart` + 3 `.v-stat-cell` metrics (*Transactions*, *Active EMIs*, *Projected / Daily Avg*) on right (`7` cols).
- **Workbench (`8/4` split on `lg+`, segmented mobile tabs `<1024px`)**:
  - **Feed Column (`8` cols)**: Triage strip (`.exp-attn`), icon-cleared search + sleek `rounded-lg` `.filter-pill` rail, subtle hairline day headers (`.exp-day-header`), and flush `1px`-divided transaction rows (with bottom mobile FAB clearance).
  - **Intelligence Rail (`4` cols)**: Category burn breakdown (`.exp-cat-row`), ruled spend highlights, trend chart (`#trendChart` auto-resized on mobile tab switch), and active EMI commitments.
- **Modal (`_expense_modal.html`, `_category_fields.html`, `_source_fields.html`)**: Ledger entry `<dialog>` with prominent amount field, Expense / Refund / Transfer segmented switch, accessible field labels, and `>=44px` touch controls.

### 2.2 `expenses/statements.html` & `expenses/statement_detail.html` (Credit Card Statement Reconciliation)
- **`statements.html`**: `.v-ledger-band` (Total Dues, Reconciled Count, Upcoming Due Dates, Gmail Sync) + card statement matrix with `Inspect` / `Unlock` actions.
- **`statement_detail.html`**: `.v-ledger-band` with 3-segment reconciliation `.v-horizon` bar (Matched Alerts vs. Imported PDF vs. Pending) + sectioned 3-stage reconciliation tables (Unmatched Lines, Reconciled Matches, Active EMIs & Fees).

### 2.3 `expenses/year.html` (Indian FY Annual Spend Matrix)
- `.fy-tabs` header + `.v-ledger-band` (FY Total Spend, Monthly Average, Peak Month, Category `.v-horizon`) + balanced FY analytics panels (flush hairline member/fixed-vs-discretionary splits without nested card borders or column height voids), Category × Month sparkline matrix, 12-month Subscription Cadence Matrix, and AI Forensic Anomaly Audit drawer.

### 2.4 `expenses/settings.html` (Ingestion, Cards, Categories & Rules Control Center)
- 2-column configuration workbench covering *Gmail OAuth Sync*, *Credit Cards & Statement PDF Passwords*, and *Categories & Merchant Categorization Rules*.

### 2.5 `tracker/dashboard.html` (Indian FY Monthly Savings & Goal Pacing Ledger)
- **Header**: FY title + date range on left; `.fy-tabs`, `Manage Goals`, and primary `+ Add Entry` on right.
- **Ledger Summary Band**: Annual Savings Goal & Achieved % + `.v-horizon` bar on left (`5` cols); *Net Savings*, *Extra Income*, *Transfers*, and *HRA Balance* on right (`7` cols).
- **Workbench**: 12-cell April–March fiscal pacing matrix, side-by-side `#barChart` and `#lineChart` panels, and paginated FY transactions & goal increments ledger.

### 2.6 `tracker/hra.html`, `tracker/notes.html` & `tracker/login.html`
- **`tracker/hra.html`**: `.v-ledger-band` (Net HRA Balance, Rent Paid, HRA Transferred, Landlord info) + chronological rent verification ledger shared across `PRIMARY`, `ACCOUNT_HOLDER`, and `LANDLORD`.
- **`tracker/notes.html`**: Collaborative household checklists and notes workspace with `>=44px` quick-add controls and active/completed sections.
- **`tracker/login.html`**: Private Bank sign-in portal with centered narrow authentication card (`max-w-[420px]`), Google SSO, inline-icon password input, and `DEBUG`-only dev-login role switcher.

---

## 3. Jewellery, Public & Admin Routes (`templates/jewellery/`, `templates/public/`, `templates/admin/`, `templates/unfold/`)

### 3.1 `jewellery/dashboard.html` & `jewellery/detail.html` (Precious Metals & Ornament Custody Ledger)
- **`dashboard.html`**: Live 24K Gold & Silver spot pills in header; `.v-ledger-band` (Collection Value + Bank Locker vs. Home Safe `.v-horizon` custody bar + Gold `g`, Silver `g`, and item count cells); single-row desktop filter toolbar (location pills, compact metal/category selects, icon-cleared search input, item count); and custody gallery rendering uploaded WebP photos when present or compact fiduciary assay cards (purity, gross/fine weight, custody badge, live bullion value) when photo-less.
- **`detail.html`**: 2-column Assay & Custody Dossier (`#viewModeContainer`: photo frame on left, ruled assay certificate on right) plus inline `#editModeContainer` form toggle.

### 3.2 `public/base.html`, `public/about.html`, `public/privacy.html`, `public/terms.html`
- Scoped `.pub-*` Private Bank Folio styling in `static/css/public.css` (`#0b0f17` ground, `#111722` `.pub-matrix` capability ledger + `.pub-spec-sheet`, `>=44px` `.pub-nav-mobile` rail on `<640px`, and 2-column `.pub-legal-grid` with sticky TOC + `68ch` `.pub-prose` measure).

### 3.3 `/vault-manage/` Admin (`pftracker/settings.py` Unfold + `templates/admin/base_site.html` + `static/css/admin_theme.css`)
- Superuser administration powered by `django-unfold` (`UNFOLD` dark Indigo sidebar navigation across Users, Savings, Portfolio, Expenses, MCP Audit Log, and OAuth tokens) paired with Vault dark ledger overrides in `admin_theme.css`.
