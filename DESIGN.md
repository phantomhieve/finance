---
name: Vault Family Office & Private Ledger System
description: High-density fiduciary ledger and private bank folio engineered for Indian household wealth intelligence
colors:
  primary: "#6366f1"
  primary-hover: "#4f46e5"
  primary-focus: "rgba(99, 102, 241, 0.22)"
  secondary: "#0ea5e9"
  accent: "#8b5cf6"
  folio-ground: "#0b0f17"
  ledger-sheet: "#111722"
  ledger-elevated: "#182030"
  ledger-hover: "#1e293b"
  ledger-glass: "rgba(17, 23, 34, 0.86)"
  ink-primary: "#f1f5f9"
  ink-secondary: "#94a3b8"
  ink-muted: "#64748b"
  hairline-subtle: "rgba(226, 232, 240, 0.07)"
  hairline-default: "rgba(226, 232, 240, 0.13)"
  hairline-strong: "rgba(226, 232, 240, 0.22)"
  gain: "#10b981"
  gain-tint: "rgba(16, 185, 129, 0.12)"
  outflow: "#f43f5e"
  outflow-tint: "rgba(244, 63, 94, 0.12)"
  caution: "#f59e0b"
  caution-tint: "rgba(245, 158, 11, 0.12)"
  bullion-gold: "#eab308"
  bullion-silver: "#94a3b8"
  equity-blue: "#6366f1"
  debt-teal: "#14b8a6"
  realty-amber: "#f97316"
typography:
  display:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "2.25rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.01em"
  body:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  label:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0.02em"
  icons:
    fontFamily: "'Material Symbols Outlined'"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  xxl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  ledger-band:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.lg}"
    padding: "20px 24px"
  panel-surface:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.lg}"
    padding: "16px 20px"
---

# Design System: Vault Family Office & Private Ledger System

## Overview

**Creative North Star: "The Private Bank Consolidated Statement & Family Office Folio"**

Vault rejects the generic SaaS dashboard cliché of floating, equal-sized cards, glowing neon halos, and decorative sparklines. Instead, its replacement visual world is modeled on an institutional **Private Bank Consolidated Portfolio Statement & Family Office Folio**: an authoritative, ruled fiduciary ledger engineered for rapid scanning, structural clarity, and zero-distraction operation.

Every screen opens with a **Full-Width Ledger Summary Band (`.v-ledger-band`)** divided by crisp 1px structural hairlines (`1px solid rgba(226, 232, 240, 0.07)`) rather than loose grids of separated cards. Inside the Ledger Band, the primary figure (`₹` net worth, monthly net spend, FY savings goal, or bullion valuation) commands immediate hierarchy alongside its period delta badge and a **Signature Multi-Segment Horizon Bar (`.v-horizon`)** that encodes asset allocation, spend pace vs. prior month, FY goal progress, or custody split in a single glance. Below the band, pages organize into purposeful **Asymmetric Workbenches (`.v-workbench`)** or **Tabbed Ledger Folios**, keeping primary tables and feeds dominant while secondary breakdowns, AI methodology notes, and mutation forms live in progressive disclosures, drawers, or side rails.

**Key Characteristics:**
- **Ruled Hairline Architecture over Card Soup**: Metrics and list items sit inside contiguous, hairline-divided strips (`.v-ledger-band`, `.v-stat-strip`, `.v-divide-list`) rather than separate floating boxes.
- **Zero-Exception Tabular Numerals**: Every rupee figure, Lakh/Crore shorthand, gram weight, percentage, and date enforces `font-variant-numeric: tabular-nums` so vertical columns lock to the pixel.
- **Signature Horizon Strip**: A proportional, color-coded horizontal bar with an inline legend appears inside the top ledger band of every major route to show composition or pacing before the user scrolls.
- **Action-Only Primary Saturation**: Sovereign Indigo (`#6366f1`) is reserved strictly for interactive primary actions, active route indicators, and focused controls — never wasted on decorative backgrounds or static labels.
- **No Eyebrow Kickers or Nested Cards**: Section headings speak directly for themselves at `1rem` (`16px`) bold without tiny uppercase kickers above them, and cards never nest inside cards.

## Colors

The palette pairs a deep obsidian folio slate (`night` mode default) and a crisp archival bond paper (`winter` mode) with high-precision semantic inks for gains, outflows, caution alerts, and Indian asset classes.

### Primary
- **Sovereign Indigo** (`#6366f1` / hover `#4f46e5`): Primary action buttons, active navigation rail indicator, active tab pills, and focus rings.

### Secondary
- **Clearing Sky** (`#0ea5e9`): Secondary analytical series, informational callouts, and inter-account transfer markers.

### Tertiary
- **Fiduciary Violet** (`#8b5cf6`): AI synthesis drawers, automated statement reconciliation indicators, and long-horizon retirement series (EPF/NPS).
- **Bullion Gold & Silver** (`#eab308` / `#94a3b8`): Dedicated commodity inks for 24K/22K gold and silver valuation strips and jewellery custody badges.

### Neutral
- **Folio Ground** (`#0b0f17` in `night`, `#f8fafc` in `winter`): The foundational viewport canvas.
- **Ledger Sheet** (`#111722` in `night`, `#ffffff` in `winter`): Primary container surface for ledger bands, workbenches, and data tables.
- **Ledger Elevated** (`#182030` in `night`, `#f1f5f9` in `winter`): Sticky table headers, input control wells, segmented tab tracks, and modal/drawer surfaces.
- **Primary Ink** (`#f1f5f9` in `night`, `#0f172a` in `winter`): High-contrast headings, primary names, and currency figures.
- **Secondary & Muted Ink** (`#94a3b8` / `#64748b`): Supporting metadata, timestamps, units, and inactive labels (maintaining ≥ 4.5:1 contrast for body copy).
- **Structural Hairlines** (`rgba(226, 232, 240, 0.07)` subtle, `rgba(226, 232, 240, 0.13)` default): 1px cell dividers and container borders.

### Semantic Inks
- **Fiduciary Emerald (Gain / Inflow / On-Pace)** (`#10b981`, tint `rgba(16, 185, 129, 0.12)`): Positive portfolio returns, net savings surplus, refunded credits, and beat-goal months.
- **Ledger Rose (Outflow / Deficit / Alert)** (`#f43f5e`, tint `rgba(244, 63, 94, 0.12)`): Spend pace overages, negative returns, missed goals, and destructive actions.
- **Caution Amber (Pending / EMI / Partial)** (`#f59e0b`, tint `rgba(245, 158, 11, 0.12)`): Active EMI commitments, pending statement reconciliations, and partial goal months.

### Named Rules
**The Action-Only Accent Rule.** Sovereign Indigo (`#6366f1`) marks things the operator can press or has selected. Never tint large hero backgrounds or static metric numbers in primary indigo; primary figures sit in crisp Primary Ink (`#f1f5f9` / `#0f172a`) while semantic delta pills carry Emerald or Rose.

**The Single-Hairline Rule.** Adjacent cells in a metric strip or ledger table share a single 1px border (`1px solid var(--v-hairline)`). Never place a thick colored `border-left` or `border-right` (>1px) on cards, callouts, or list rows.

## Typography

**Display & UI Font:** `Inter` (with `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` fallback)
**Icon System:** `Material Symbols Outlined` (20px default UI size, consistent 400 weight; filled variant on active nav states)

**Character:** A single, disciplined sans-serif workhorse tuned with tight display tracking for large rupee figures and strict `tabular-nums` discipline across all data tables, badges, and inputs.

### Hierarchy
- **Display Figure** (`700`, `2.25rem` / `36px`, line-height `1.15`, tracking `-0.03em`, `tabular-nums`): The single lead monetary figure inside a page's Ledger Band.
- **Page Headline** (`700`, `1.5rem` / `24px`, line-height `1.25`, tracking `-0.02em`): Route title in the Page Header bar.
- **Section Title** (`600`, `1rem` / `16px`, line-height `1.35`, tracking `-0.01em`): Direct panel and workbench headings.
- **Body & Table Data** (`400` / `500`, `0.875rem` / `14px`, line-height `1.5`, `tabular-nums` on numbers): Ledger rows, descriptions, and form controls (prose constrained to `65ch`).
- **Column & Cell Label** (`600`, `0.75rem` / `12px`, line-height `1.35`, tracking `0.02em`): Table column headers, stat cell labels, and filter pills.

### Named Rules
**The No-Kicker Rule.** Never place a small uppercase eyebrow or kicker label above a page headline or section title. A heading carries its own hierarchy; let the title and its inline count or subtitle speak directly.

**The Tabular Lock Rule.** Every element displaying currency (`₹`), percentages (`%`), weights (`g`), land units (`Gaj`, `Bigha`, `Sq.ft`), quantities, or dates MUST apply `font-variant-numeric: tabular-nums`.

## Layout

Vault uses a structural, responsive shell designed for both wide desktop monitors (`1280px–1600px+`) and one-handed mobile PWA operation (`390px–430px`):

- **Desktop Left Navigation Rail (`aside#desktopSidebar`, ≥1024px)**: Fixed `240px` width (collapses smoothly to `64px` icon rail). Organized into domain groups (Wealth & Portfolio, Cashflow & Tax, Workspace) with a compact user/role footer and quick lock indicator.
- **Sticky Utility Topbar (`header.v-topbar`, `56px` height)**: Displays current route context/breadcrumbs on desktop, brand identity on mobile, vault session lock status timer when unlocked, quick theme switch, and user account menu.
- **Main Stage Container (`max-w-[1440px] mx-auto px-4 lg:px-8`)**: Generous horizontal breathing room with a consistent vertical rhythm (`24px` between major zones, `16px` inside workbenches).
- **Page Structure Grammar**:
  1. **Page Header (`.v-page-header`)**: Route title + subtitle on the left; primary period switcher (FY tabs / Month switcher) and compact action toolbar on the right.
  2. **Ledger Summary Band (`.v-ledger-band`)**: Full-width ruled container with lead metric + delta badge + Horizon Bar on the left (`5` cols) and a `1px` hairline-divided grid of 3–4 secondary KPI cells on the right (`7` cols).
  3. **Primary Workbench (`.v-workbench`)**: Either an asymmetric 2-column split (`8 cols` primary ledger/feed + `4 cols` sticky analytical rail) or a segmented tabbed workspace (Overview / Holdings / Analytics / AI Audit).
- **Mobile Ergonomic Adaptation (<1024px)**: The sidebar hides in favor of a fixed bottom dock (`nav.dock`) with 5 core destinations. Data tables either keep pinned primary columns with clean horizontal scroll or transform into structured `.v-mobile-row` ledger items without losing numeric alignment.

## Elevation & Depth

Vault relies on **tonal surface layering and crisp 1px structural hairlines** rather than heavy drop shadows or glowing borders. Surfaces at rest sit flat on the Folio Ground (`#0b0f17`), separated by luminance steps (`#111722` sheet → `#182030` elevated well) and subtle borders. Shadows appear only on floating overlays (dropdown menus, slide-over drawers, and modal dialogs).

### Shadow Vocabulary
- **Resting Panel** (`box-shadow: none; border: 1px solid rgba(226, 232, 240, 0.07)`): All ledger bands, workbench panels, and tables at rest.
- **Interactive Lift** (`box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.35), 0 2px 6px rgba(0, 0, 0, 0.2)`): Applied only to clickable navigation tiles or floating popovers on hover.
- **Overlay & Drawer** (`box-shadow: 0 24px 48px -12px rgba(0, 0, 0, 0.65), 0 4px 16px rgba(0, 0, 0, 0.35)`): Slide-over drawers and `<dialog>` modals over a dimmed backdrop (`rgba(5, 8, 15, 0.72)` with `backdrop-filter: blur(6px)`).

### Named Rules
**The Flat-At-Rest Rule.** Panels, metric strips, and tables never cast drop shadows at rest and never jump upward (`translateY`) when hovered unless the entire panel is an anchor link to another route.

## Shapes

- **Control Radius (`8px` / `0.5rem`)**: Buttons, inputs, selects, and segmented tab buttons use a crisp, tailored `8px` radius.
- **Panel & Ledger Band Radius (`12px` / `0.75rem`)**: Primary containers (`.v-ledger-band`, `.v-panel`, `.v-table-wrap`) use a tight `12px` radius with `overflow: hidden` so internal `1px` cell hairlines meet the outer border cleanly.
- **Drawer & Modal Radius (`16px` / `1rem`)**: Dialog boxes and bottom/side sheets.
- **Delta & Filter Pills (`9999px`)**: Compact status badges, percentage delta pills, and selectable filter chips.

## Components

### Buttons (`.btn`, `.v-btn`)
- **Shape:** Tailored `8px` radius (`rounded-lg`), `36px` (`btn-sm`) standard toolbar height, `42px` form submit height.
- **Primary:** Sovereign Indigo (`#6366f1`) fill with crisp `#ffffff` text (`padding: 8px 16px`). Reserved for the single primary action on a screen (e.g., `+ Add Expense`, `+ Add Holding`).
- **Secondary / Toolbar (`.v-btn-secondary` / `btn-ghost`)**: Subtle surface fill (`rgba(226, 232, 240, 0.05)`) with `1px` border (`rgba(226, 232, 240, 0.10)`), `#f1f5f9` text, shifting to `rgba(226, 232, 240, 0.10)` on hover.

### Ledger Summary Band & Stat Strip (`.v-ledger-band`, `.v-stat-grid`, `.v-stat-cell`)
- **Character:** The signature opening component of every Vault page — a unified, hairline-ruled statement header.
- **Structure:** Outer container in Ledger Sheet (`#111722`) with `12px` radius and `1px` border. Internal cells separated by `1px solid rgba(226, 232, 240, 0.07)` (using CSS grid `gap: 1px` on a hairline-colored track or border utilities).
- **Content:** Lead cell displays label (`12px` muted), Display Figure (`36px` bold `tabular-nums`), semantic delta badge (`.v-delta`), and optional `.v-horizon` bar. Adjacent cells show supporting metrics (`20px` bold `tabular-nums`) with secondary subtext.

### Signature Horizon Bar (`.v-horizon`, `.v-horizon-legend`)
- **Character:** Multi-segment proportional bar (`8px` height, `4px` radius, `2px` gap between segments) encoding asset class weights, spend category shares, or goal completion, paired with a compact inline dot-legend below it.

### Workbench Panels (`.v-panel`, `.v-panel-header`, `.v-panel-body`)
- **Corner Style:** `12px` radius, `1px` border (`rgba(226, 232, 240, 0.07)`), background `#111722`.
- **Header:** Flex row with `16px` (`1rem`) semibold title on the left, optional count badge or inline filter/action controls on the right, separated from body by a `1px` hairline when wrapping a table or list.
- **No Nesting:** A `.v-panel` never contains another `.v-panel` or `.card`; internal subdivisions use `1px` hairline dividers (`.v-divide-list` or `.v-stat-strip`).

### Data Tables (`.v-table-wrap`, `.v-table`)
- **Style:** Full-width edge-to-edge inside a `.v-panel`. Sticky header row (`#182030`) with `11px` uppercase tracked column labels (`0.04em`). Numeric columns right-aligned (`text-right tabular-nums`).
- **States:** Row hover (`rgba(226, 232, 240, 0.035)`), totals footer row (`font-semibold` with top `1px` strong hairline), and clean pagination footer.

### Slide-Over Drawers & Modals (`dialog.modal`, `.v-drawer`)
- **Style:** Native `<dialog>` elements styled either as a centered command modal (`max-w-lg rounded-2xl`) or a right-hand slide-over sheet (`.v-modal-drawer`: pinned to the right edge of the viewport, full height, `max-w-xl`) for multi-field forms, transaction inspection, and statement line reconciliation.

### Inputs & Form Fields (`.form-field`, `.v-input`)
- **Style:** `42px` height, `8px` radius, `1px` border (`rgba(226, 232, 240, 0.14)`), `#0b0f17` (`night`) or `#ffffff` (`winter`) background.
- **Focus:** `border-color: #6366f1` with `0 0 0 3px rgba(99, 102, 241, 0.18)` ring.

## Do's and Don'ts

### Do:
- **Do** open every primary dashboard and detail page with a `.v-ledger-band` (or `.v-stat-strip` on subpages) that presents the primary figure, delta, and `.v-horizon` bar in one unified, hairline-ruled block.
- **Do** right-align all monetary amounts, percentages, and weights in tables and list rows, and enforce `tabular-nums` on every numeric element.
- **Do** group secondary actions (Sync Sheets, Refresh Prices, Export, Biometrics) into a clean action bar or overflow menu so the primary CTA stands alone.
- **Do** use asymmetric 2-column workbenches (`8/4` or `7/5` split on `lg+`) or segmented tabs to prevent endless vertical scrolling of stacked full-width boxes.
- **Do** preserve every Django template block, URL tag, CSRF token, form field name, and JS hook (`openModal`, `closeModal`, `confirmDelete`, `initPagination`, Chart.js canvas IDs).

### Don't:
- **Don't** nest cards inside cards (e.g., putting bordered `.stat-card` boxes with gradients inside a `.card.hero-gradient`). Use hairline-divided `.v-stat-cell` segments inside `.v-ledger-band` instead.
- **Don't** place a small uppercase kicker/eyebrow label above an `<h1>`, `<h2>`, or `<h3>` heading.
- **Don't** use thick colored left borders (`border-l-4`) on callouts, AI insights, or transaction rows; use a `1px` border with a subtle semantic tint fill (`8%`) and a crisp status badge or icon dot.
- **Don't** use gradient text (`bg-clip-text`) or animated shimmer lines on financial headers.
- **Don't** use raw emoji (`📈`, `💳`, `🏠`) as UI icons; use `Material Symbols Outlined` or authored inline SVG everywhere.
