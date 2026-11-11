# Vault Component Library (`docs/ux/components.md`)

Shared HTML/CSS component patterns for the **Vault Family Office & Private Ledger System**.
Defined in `static/css/style.css` alongside Tailwind CSS v4 (`@tailwindcss/browser@4`) and DaisyUI 5 (`night` / `winter` themes).

---

## 1. Page Header (`.v-page-header`)

Displays the route title, subtitle, period switchers, and contextual action toolbar (at most one `.v-btn-primary` per header).

```html
<div class="v-page-header">
  <div>
    <h1 class="v-title">Master Portfolio</h1>
    <p class="v-subtitle">Consolidated balance sheet &amp; asset holdings</p>
  </div>
  <div class="v-toolbar">
    <button type="button" class="v-btn v-btn-secondary">
      <span class="material-symbols-outlined text-[17px]">sync</span>Sync Sheets
    </button>
    <button type="button" class="v-btn v-btn-secondary">
      <span class="material-symbols-outlined text-[17px]">currency_exchange</span>Refresh Prices
    </button>
    <a href="{% url 'portfolio_growth' %}" class="v-btn v-btn-primary">
      <span class="material-symbols-outlined text-[17px]">trending_up</span>Growth Analysis
    </a>
  </div>
</div>
```

---

## 2. Signature Ledger Summary Band (`.v-ledger-band`)

Contiguous hairline-ruled statement header pairing the primary Display Figure, delta badge, `.v-horizon` bar, and 3–4 `.v-stat-cell` KPIs.

```html
<div class="v-ledger-band">
  <div class="v-lead-cell">
    <div class="v-lead-label">
      <span>Total Portfolio Value</span>
      <label class="flex items-center gap-1.5 cursor-pointer text-xs normal-case opacity-75">
        <span>Real Estate</span>
        <input type="checkbox" class="toggle toggle-primary toggle-xs" checked>
      </label>
    </div>
    <div class="v-lead-figure-row">
      <span class="v-lead-figure">{{ total_value|inr }}</span>
      <span class="v-delta v-delta-pos">
        <span class="material-symbols-outlined text-xs">trending_up</span>
        +{{ total_returns|inr }} ({{ return_pct }}%)
      </span>
    </div>
    <div class="v-lead-sub">Net change across all 11 asset classes</div>

    <div class="v-horizon">
      <div class="v-horizon-bar">
        <span class="v-horizon-seg" style="width: 48%; background: var(--v-equity);" title="Equity: 48%"></span>
        <span class="v-horizon-seg" style="width: 26%; background: var(--v-debt);" title="Retirement & Debt: 26%"></span>
        <span class="v-horizon-seg" style="width: 14%; background: var(--v-gold);" title="Gold: 14%"></span>
        <span class="v-horizon-seg" style="width: 12%; background: var(--v-realty);" title="Real Estate: 12%"></span>
      </div>
      <div class="v-horizon-legend">
        <div class="v-horizon-item">
          <span class="v-horizon-dot" style="background: var(--v-equity);"></span>
          <span>Equity:</span>
          <span class="v-horizon-amount">₹68.5 L</span>
          <span class="v-horizon-pct">(48%)</span>
        </div>
        <div class="v-horizon-item">
          <span class="v-horizon-dot" style="background: var(--v-debt);"></span>
          <span>Debt &amp; EPF:</span>
          <span class="v-horizon-amount">₹37.1 L</span>
          <span class="v-horizon-pct">(26%)</span>
        </div>
      </div>
    </div>
  </div>

  <div class="v-stat-grid">
    <div class="v-stat-cell">
      <div class="v-stat-label">Invested Capital</div>
      <div class="v-stat-value">{{ total_invested|inr }}</div>
      <div class="v-stat-sub">Active holdings</div>
    </div>
    <div class="v-stat-cell">
      <div class="v-stat-label">Unrealized Returns</div>
      <div class="v-stat-value text-emerald-400">+{{ total_returns|inr }}</div>
      <div class="v-stat-sub">+14.2% annualized</div>
    </div>
    <div class="v-stat-cell">
      <div class="v-stat-label">FY Performance</div>
      <div class="v-stat-value">{{ fy_performance.total_change|inr }}</div>
      <div class="v-stat-sub">{{ fy_performance.money_added|inr_short }} added · {{ fy_performance.market_gain|inr_short }} market</div>
    </div>
    <div class="v-stat-cell">
      <div class="v-stat-label">Goal Funding</div>
      <div class="v-stat-value text-indigo-400">82.4%</div>
      <div class="v-stat-sub">3 of 4 milestones on track</div>
    </div>
  </div>
</div>
```

---

## 3. Standalone Ruled Stat Strip (`.v-stat-strip`)

Compact 3- or 4-cell ruled KPI strip for secondary routes and sub-tabs (odd trailing cells automatically span full width on 2-column mobile/tablet breakpoints).

```html
<div class="v-stat-strip">
  <div class="v-stat-cell">
    <div class="v-stat-label">Total Spend (FY)</div>
    <div class="v-stat-value">{{ total_spent|inr }}</div>
    <div class="v-stat-sub">12 months</div>
  </div>
  <div class="v-stat-cell">
    <div class="v-stat-label">Monthly Average</div>
    <div class="v-stat-value">{{ monthly_avg|inr }}</div>
    <div class="v-stat-sub">Paced against target</div>
  </div>
  <div class="v-stat-cell">
    <div class="v-stat-label">Highest Month</div>
    <div class="v-stat-value text-rose-400">{{ peak_month.amount|inr }}</div>
    <div class="v-stat-sub">{{ peak_month.name }}</div>
  </div>
  <div class="v-stat-cell">
    <div class="v-stat-label">Active EMIs</div>
    <div class="v-stat-value text-amber-400">{{ emi_count }}</div>
    <div class="v-stat-sub">{{ emi_monthly|inr_short }}/month</div>
  </div>
</div>
```

---

## 4. Status & Delta Pills (`.v-delta`)

```html
<span class="v-delta v-delta-pos">
  <span class="material-symbols-outlined text-xs">trending_up</span>+₹1,24,000 (8.5%)
</span>
<span class="v-delta v-delta-neg">
  <span class="material-symbols-outlined text-xs">trending_down</span>−₹18,500 (2.1%)
</span>
<span class="v-delta v-delta-caution">
  <span class="material-symbols-outlined text-xs">schedule</span>Day 18 of 31 · Ahead
</span>
<span class="v-delta v-delta-neutral">
  <span>Bank Locker</span>
</span>
```

---

## 5. Workbench Container (`.v-panel`) & Asymmetric Grid (`.v-workbench`)

`.v-panel` sits flat at rest (`min-width: 0`, `align-self: start` in grid layouts while respecting explicit `max-w-*` utility constraints on centered cards such as `/login/` and `/portfolio/unlock/`). Never nest bordered cards inside `.v-panel`; divide internal rows with `1px` structural hairlines (`divide-[var(--v-hairline-subtle)]` or `.v-divide-list`).

```html
<div class="v-workbench">
  <div class="v-workbench-main">
    <div class="v-panel">
      <div class="v-panel-header">
        <h2 class="v-panel-title">
          <span class="material-symbols-outlined text-base text-indigo-400">cases</span>
          Indian Equities &amp; Mutual Funds
        </h2>
        <a href="{% url 'portfolio_zerodha_consolidated' %}" class="v-btn v-btn-ghost v-btn-xs">
          View Blotter <span class="material-symbols-outlined text-xs">arrow_forward</span>
        </a>
      </div>
      <div class="v-panel-table">
        <table class="v-table">...</table>
      </div>
    </div>
  </div>

  <div class="v-workbench-rail">
    <div class="v-panel">
      <div class="v-panel-header">
        <h2 class="v-panel-title">Allocation Highlights</h2>
      </div>
      <div class="divide-y divide-[var(--v-hairline-subtle)]">
        <div class="px-5 py-3.5 text-sm">Flush hairline-divided row</div>
      </div>
    </div>
  </div>
</div>
```

---

## 6. High-Density Data Tables (`.v-table`, `.v-table-sticky`, `.v-table-stack`) & Mobile Rows (`.v-mobile-row`)

Responsive mobile table primitives (`360px–430px` & `768px`):
1. **`.v-table-wrap.v-table-sticky`**: Pure-CSS horizontal scroll shadows + pinned sticky column 1 (`max-width: 44vw` on `<768px`).
2. **`.v-table.v-table-stack`**: Card-stack transformation below `640px` rendering `td[data-label]` labels on the left and `tabular-nums` values on the right.
3. **`.v-col-hide-sm` / `.v-col-hide-md`** & **`.v-mobile-row`**: Prune secondary columns or render compact `md:hidden` 2-column ledger rows synced with `initPagination()`.

```html
<div class="v-table-wrap v-table-sticky">
  <table class="v-table">
    <thead>
      <tr>
        <th>Holding / Instrument</th>
        <th class="v-col-hide-sm">Category</th>
        <th class="v-num v-col-hide-sm">Qty</th>
        <th class="v-num">Current</th>
        <th class="v-num">P&amp;L</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="font-medium">HDFC Bank Ltd</td>
        <td class="v-col-hide-sm"><span class="v-delta v-delta-neutral">Equity</span></td>
        <td class="v-num v-col-hide-sm">150</td>
        <td class="v-num font-semibold">₹2,58,000</td>
        <td class="v-num text-emerald-400 font-semibold">+₹30,000 (+13.2%)</td>
      </tr>
    </tbody>
  </table>
</div>

<div class="v-panel md:hidden">
  <div class="divide-y divide-[var(--v-hairline-subtle)]">
    <a href="#" class="v-mobile-row">
      <div>
        <div class="text-xs font-semibold text-base-content">HDFC Bank Ltd</div>
        <div class="text-[11px] text-base-content/60">150 shares · Avg ₹1,520</div>
      </div>
      <div class="text-right">
        <div class="text-xs font-bold tabular-nums">₹2,58,000</div>
        <div class="text-[11px] text-emerald-400 font-semibold tabular-nums">+₹30,000 (+13.2%)</div>
      </div>
    </a>
  </div>
</div>
```

---

## 7. Inputs, Icon Wrappers & Filter Chips (`.v-input`, `.filter-pill`, `.v-pill-rail`)

- **Leading Search Icon & Trailing Password Toggle**: Wrap inputs in a `relative` container with explicit horizontal padding clearance (`pl-10` for leading search icons, `pr-11` for inline password visibility buttons anchored `absolute right-1 inset-y-0 my-auto`) so icons sit cleanly inside the field without overlapping text.
- **Filter Chips (`.filter-pill`, `.v-pill-rail`)**: Sleek `rounded-lg` (`8px`) filter chips inside touch-scrollable `.v-pill-rail` rails with trailing scroll padding and `>=44px` touch ergonomics.

```html
<div class="v-filter-bar">
  <div class="relative flex-1 min-w-[200px]">
    <span class="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-base-content/50">search</span>
    <input type="search" class="v-input w-full pl-10" placeholder="Search holdings or merchants...">
  </div>
  <div class="v-pill-rail" role="group" aria-label="Filter by location">
    <button type="button" class="filter-pill is-active">All</button>
    <button type="button" class="filter-pill">Bank Locker</button>
    <button type="button" class="filter-pill">Home Safe</button>
  </div>
</div>
```

---

## 8. Segmented Switchers, Disclosures, Modals & Shell Utilities

- **Segmented Switcher (`.v-segmented` / `.v-segmented-item.is-active`)**: Compact route or view-mode toggle bar.
- **Progressive Disclosure (`<details class="v-disclosure">`)**: Collapsible methodology, audit finding, or raw log section.
- **Modals & Slide-Over Drawers (`dialog.modal`, `.v-modal-drawer`)**: Centered dialogs (`<768px` auto-docked as bottom sheets with `max-height: 92dvh`, sticky `.v-modal-header`, and safe-area `.v-modal-footer`) or right-pinned `.v-modal-drawer` sheets, controlled via `openModal(id)` and `closeModal(id)`.
- **Mobile Shell (`nav.v-mobile-dock` + `#mobileNavDrawer`)**: Fixed 5-slot bottom dock (`>=56px` + `safe-area-inset-bottom`) + slide-up full route sheet.
- **Toast Feedback & Theme Events**: `Vault.toast(message, level)` renders non-shifting alerts in `#vaultToastRegion`; `toggleVaultTheme()` dispatches `vault:themechange` so `charts.js` and `expenses.js` re-theme live between `night` and `winter`.
