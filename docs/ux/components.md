# Vault Component Library (`docs/ux/components.md`)

This is the shared component system for the **Vault Family Office & Private Ledger Redesign**.
All page designers (`@ui-1` portfolio, `@ui-2` cashflow/expenses/tracker, `@ui-3` jewellery/public/admin) must build against these patterns.

All components are defined in `static/css/style.css` and use native Tailwind CSS utilities + DaisyUI 5 tokens.

---

## 1. Page Header (`.v-page-header`)

Displays the route title, subtitle, period switchers, and contextual action buttons.

```html
<div class="v-page-header">
  <div>
    <h1 class="v-title">Master Portfolio</h1>
    <p class="v-subtitle">Consolidated balance sheet &amp; asset holdings</p>
  </div>
  <div class="v-toolbar">
    <!-- Secondary toolbar actions -->
    <button type="button" class="v-btn v-btn-secondary">
      <span class="material-symbols-outlined text-[17px]">sync</span>Sync Sheets
    </button>
    <button type="button" class="v-btn v-btn-secondary">
      <span class="material-symbols-outlined text-[17px]">currency_exchange</span>Refresh Prices
    </button>
    <!-- Primary CTA (at most ONE per header) -->
    <a href="{% url 'portfolio_growth' %}" class="v-btn v-btn-primary">
      <span class="material-symbols-outlined text-[17px]">trending_up</span>Growth Analysis
    </a>
  </div>
</div>
```

---

## 2. Signature Ledger Summary Band (`.v-ledger-band`)

The hallmark opening component of every Vault dashboard and major section. Replaces floating card soup with a single, contiguous ruled statement header.

```html
<div class="v-ledger-band">
  <!-- Left Lead Cell (approx 5 cols on lg+) -->
  <div class="v-lead-cell">
    <div class="v-lead-label">
      <span>Total Portfolio Value</span>
      <!-- Optional inline toggle/filter -->
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

    <!-- Signature Horizon Bar -->
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
          <span class="v-horizon-amount">₹68.5L</span>
          <span class="v-horizon-pct">(48%)</span>
        </div>
        <div class="v-horizon-item">
          <span class="v-horizon-dot" style="background: var(--v-debt);"></span>
          <span>Debt &amp; EPF:</span>
          <span class="v-horizon-amount">₹37.1L</span>
          <span class="v-horizon-pct">(26%)</span>
        </div>
        <div class="v-horizon-item">
          <span class="v-horizon-dot" style="background: var(--v-gold);"></span>
          <span>Bullion:</span>
          <span class="v-horizon-amount">₹20.0L</span>
          <span class="v-horizon-pct">(14%)</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Right Hairline Grid (approx 7 cols, 3 or 4 .v-stat-cell cells) -->
  <div class="v-stat-grid">
    <div class="v-stat-cell">
      <div class="v-stat-label">Invested Capital</div>
      <div class="v-stat-value">{{ total_invested|inr }}</div>
      <div class="v-stat-sub">Across 42 active holdings</div>
    </div>
    <div class="v-stat-cell">
      <div class="v-stat-label">Unrealized Returns</div>
      <div class="v-stat-value text-emerald-400">+{{ total_returns|inr }}</div>
      <div class="v-stat-sub">+14.2% annualized</div>
    </div>
    <div class="v-stat-cell">
      <div class="v-stat-label">FY 25-26 Performance</div>
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

Use for sub-pages or secondary tabs where a smaller 3 or 4 cell KPI bar is needed.

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
<!-- Positive Gain / On Pace -->
<span class="v-delta v-delta-pos">
  <span class="material-symbols-outlined text-xs">trending_up</span>+₹1,24,000 (8.5%)
</span>

<!-- Negative Outflow / Over Pace -->
<span class="v-delta v-delta-neg">
  <span class="material-symbols-outlined text-xs">trending_down</span>-₹18,500 (2.1%)
</span>

<!-- Caution / Pending -->
<span class="v-delta v-delta-caution">
  <span class="material-symbols-outlined text-xs">schedule</span>Day 18 of 31 · Ahead
</span>

<!-- Neutral -->
<span class="v-delta v-delta-neutral">
  <span>Bank Locker</span>
</span>
```

---

## 5. Workbench Container (`.v-panel`)

The standard card/panel container. Eliminates nested borders and ensures consistent headers.

```html
<div class="v-panel">
  <div class="v-panel-header">
    <h2 class="v-panel-title">
      <span class="material-symbols-outlined text-base text-indigo-400">cases</span>
      Indian Equities &amp; Mutual Funds
    </h2>
    <div class="flex items-center gap-2">
      <span class="text-xs text-base-content/50 font-mono">3 Accounts</span>
      <a href="{% url 'portfolio_zerodha_consolidated' %}" class="v-btn v-btn-ghost v-btn-xs">
        View Blotter <span class="material-symbols-outlined text-xs">arrow_forward</span>
      </a>
    </div>
  </div>
  
  <!-- Use .v-panel-body for standard padded content -->
  <div class="v-panel-body">
    <p class="text-sm text-base-content/70">Panel body content goes here.</p>
  </div>

  <!-- OR use .v-panel-table when embedding a table edge-to-edge -->
  <div class="v-panel-table">
    <table class="v-table">...</table>
  </div>

  <!-- Optional footer -->
  <div class="v-panel-footer">
    <span>Last updated: 10 mins ago</span>
    <button class="v-btn v-btn-ghost v-btn-xs">Export CSV</button>
  </div>
</div>
```

---

## 6. Asymmetric Workbench Grid (`.v-workbench`)

Organizes complex screens into a 2-column layout on desktop (`7fr 5fr`, `.v-workbench-8-4` for `8fr 4fr`, or `.v-workbench-equal` for `1fr 1fr`). Columns align to `start` with natural content height, preventing giant empty voids when adjacent panels have uneven length.

```html
<div class="v-workbench">
  <!-- Left Primary Work Area (e.g. Ledger table or transaction feed) -->
  <div class="v-workbench-main">
    <div class="v-panel">...</div>
  </div>

  <!-- Right Contextual Rail (e.g. Analytics, AI Score, Highlights) -->
  <div class="v-workbench-rail">
    <div class="v-panel">...</div>
  </div>
</div>
```

---

## 7. Institutional High-Density Data Table (`.v-table`)

For responsive tables, add `.v-col-hide-sm` to hide non-essential secondary columns below 640px, or `.v-col-hide-md` below 768px. Touch scrolling is enabled by default on `.v-table-wrap`.

```html
<div class="v-table-wrap">
  <table class="v-table">
    <thead>
      <tr>
        <th>Holding / Instrument</th>
        <th class="v-col-hide-sm">Category</th>
        <th class="v-num v-col-hide-sm">Qty</th>
        <th class="v-num v-col-hide-md">Avg Price</th>
        <th class="v-num">Current</th>
        <th class="v-num">P&amp;L</th>
        <th class="text-center">Action</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="font-medium">
          <div class="font-semibold text-base-content">HDFC Bank Ltd</div>
          <div class="text-[11px] text-base-content/50">INE040A01034</div>
        </td>
        <td><span class="v-delta v-delta-neutral">Equity</span></td>
        <td class="v-num">150</td>
        <td class="v-num">₹1,520.00</td>
        <td class="v-num font-semibold">₹2,58,000</td>
        <td class="v-num text-emerald-400 font-semibold">+₹30,000 (+13.2%)</td>
        <td class="text-center">
          <button class="v-btn v-btn-ghost v-btn-xs">Edit</button>
        </td>
      </tr>
    </tbody>
    <tfoot>
      <tr>
        <td colspan="4">Total Portfolio Equity</td>
        <td class="v-num">₹68,50,000</td>
        <td class="v-num text-emerald-400">+₹9,40,000</td>
        <td></td>
      </tr>
    </tfoot>
  </table>
</div>
```

---

## 8. Mobile List Row (`.v-mobile-row`)

For mobile viewports (`hidden md:table` / `md:hidden`), render high-density list items that preserve tabular alignment:

```html
<div class="v-panel md:hidden">
  <div class="v-panel-header">
    <h3 class="v-panel-title">Holdings</h3>
  </div>
  <div class="divide-y divide-base-content/6">
    <a href="#" class="v-mobile-row">
      <div>
        <div class="text-xs font-semibold text-base-content">HDFC Bank Ltd</div>
        <div class="text-[11px] text-base-content/50">150 shares · Avg ₹1,520</div>
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

## 9. Buttons (`.v-btn`)

```html
<!-- Primary action (use sparingly, max 1 per view) -->
<button class="v-btn v-btn-primary">
  <span class="material-symbols-outlined text-[17px]">add</span>Add Transaction
</button>

<!-- Secondary toolbar action -->
<button class="v-btn v-btn-secondary">
  <span class="material-symbols-outlined text-[17px]">tune</span>Filters
</button>

<!-- Ghost / Quiet utility -->
<button class="v-btn v-btn-ghost v-btn-sm">
  <span class="material-symbols-outlined text-[15px]">edit</span>Edit
</button>

<!-- Destructive action -->
<button class="v-btn v-btn-danger v-btn-sm">
  <span class="material-symbols-outlined text-[15px]">delete</span>Delete
</button>
```

---

## 10. Segmented Pill Switcher (`.v-segmented`)

```html
<div class="v-segmented">
  <a href="?view=master" class="v-segmented-item is-active">
    <span class="material-symbols-outlined text-sm">wallet</span>Master Portfolio
  </a>
  <a href="?view=child" class="v-segmented-item">
    <span class="material-symbols-outlined text-sm">child_care</span>Child Portfolio
  </a>
</div>
```

---

## 11. Progressive Disclosure (`.v-disclosure`)

Tuck deep technical notes, AI reasoning, or raw reconciliation logs out of the main scan path:

```html
<details class="v-disclosure">
  <summary>
    <span>AI Portfolio Risk &amp; Methodology Notes</span>
    <span class="material-symbols-outlined text-sm transition-transform group-open:rotate-180">expand_more</span>
  </summary>
  <div class="v-disclosure-content">
    <p>Detailed multi-stage AI reasoning, asset classification breakdown, and tax loss harvesting opportunities.</p>
  </div>
</details>
```

---

## 12. Slide-Over Drawer (`.v-modal-drawer`)

Use native HTML `<dialog>` with `.v-modal-drawer` for complex forms or inspectors:

```html
<dialog id="holdingDrawer" class="modal v-modal-drawer">
  <div class="modal-box w-full max-w-lg bg-base-100 p-6 flex flex-col justify-between">
    <div>
      <div class="flex items-center justify-between pb-4 border-b border-base-content/8">
        <h3 class="font-bold text-base">Add New Holding</h3>
        <button class="v-btn v-btn-ghost v-btn-xs" onclick="closeModal('holdingDrawer')">
          <span class="material-symbols-outlined text-lg">close</span>
        </button>
      </div>
      <form class="v-form-grid mt-4">
        <div class="v-field">
          <label class="v-label">Instrument Name</label>
          <input type="text" class="v-input" placeholder="e.g. Parag Parikh Flexi Cap">
        </div>
        <div class="v-form-grid-2">
          <div class="v-field">
            <label class="v-label">Units</label>
            <input type="number" class="v-input" placeholder="0.00">
          </div>
          <div class="v-field">
            <label class="v-label">Cost Price (₹)</label>
            <input type="text" class="v-input" placeholder="₹0.00">
          </div>
        </div>
      </form>
    </div>
    <div class="flex justify-end gap-2 pt-4 border-t border-base-content/8 mt-6">
      <button class="v-btn v-btn-ghost" onclick="closeModal('holdingDrawer')">Cancel</button>
      <button class="v-btn v-btn-primary">Save Holding</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
```

---

## 13. Purposeful Empty State (`.v-empty`)

```html
<div class="v-empty">
  <div class="v-empty-icon">
    <span class="material-symbols-outlined text-2xl">receipt_long</span>
  </div>
  <h3 class="v-empty-title">No expenses recorded for this month</h3>
  <p class="v-empty-desc">Connect Gmail sync to automatically ingest card alerts, or manually log your first transaction.</p>
  <button class="v-btn v-btn-primary" onclick="Expenses.open()">
    <span class="material-symbols-outlined text-[17px]">add</span>Add First Expense
  </button>
</div>
```
