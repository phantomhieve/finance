---
name: Vault Family Office & Private Ledger System
description: High-density fiduciary ledger and private bank folio engineered for Indian household wealth intelligence
colors:
  primary: "#6366f1"
  primary-hover: "#4f46e5"
  button-primary-bg: "#4f46e5"
  button-primary-hover: "#4338ca"
  primary-focus: "rgba(99, 102, 241, 0.24)"
  secondary: "#0ea5e9"
  accent: "#8b5cf6"
  folio-ground: "#0b0f17"
  ledger-sheet: "#111722"
  ledger-elevated: "#182030"
  ledger-hover: "#1e293b"
  ledger-glass: "rgba(17, 23, 34, 0.90)"
  ink-primary: "#f1f5f9"
  ink-secondary: "#cbd5e1"
  ink-muted: "#94a3b8"
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
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.45
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
    backgroundColor: "{colors.button-primary-bg}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.button-primary-hover}"
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

Vault is modeled on an institutional **Private Bank Consolidated Portfolio Statement & Family Office Folio**: an authoritative, ruled fiduciary ledger engineered for rapid scanning, structural clarity, and zero-distraction operation.

Every primary screen opens with a **Full-Width Ledger Summary Band (`.v-ledger-band`)** divided by crisp 1px structural hairlines (`1px solid var(--v-hairline-subtle)`). Inside the Ledger Band, the primary figure (`₹` net worth, monthly net spend, FY savings goal, or bullion valuation) commands immediate hierarchy alongside its period delta badge and a **Signature Multi-Segment Horizon Bar (`.v-horizon`)** that encodes asset allocation, spend pace vs. prior month, FY goal progress, or custody split in a single glance. Below the band, pages organize into balanced **Asymmetric Workbenches (`.v-workbench`)** or **Tabbed Ledger Folios**, keeping primary tables and feeds dominant while secondary breakdowns, AI methodology notes, and mutation forms live in progressive disclosures, drawers, or side rails.

**Key Characteristics:**
- **Ruled Hairline Architecture over Card Soup**: Metrics and list items sit inside contiguous, hairline-divided strips (`.v-ledger-band`, `.v-stat-strip`, `.v-divide-list`) rather than separate floating boxes.
- **Zero-Exception Tabular Numerals**: Every rupee figure, Lakh/Crore shorthand, gram weight, percentage, and date enforces `font-variant-numeric: tabular-nums` so vertical columns lock to the pixel.
- **Signature Horizon Strip**: A proportional, color-coded horizontal bar with an inline legend appears inside the top ledger band of every major route to show composition or pacing before scrolling.
- **Action-Only Primary Saturation**: Sovereign Indigo (`#6366f1` rings/indicators; `#4f46e5` WCAG AA button fill) is reserved strictly for interactive primary actions, active route indicators, and focused controls — never decorative backgrounds or static labels.
- **No Eyebrow Kickers or Nested Cards**: Section headings speak directly at `1rem` (`16px`) semibold without tiny uppercase kickers above them, and bordered cards never nest inside `.v-panel` containers.

## Colors

The palette pairs a deep obsidian folio slate (`night` mode default) and a crisp archival bond paper (`winter` mode) with high-precision semantic inks for gains, outflows, caution alerts, and Indian asset classes.

### Primary
- **Sovereign Indigo** (`--v-primary: #6366f1`, button fill `--v-btn-primary-bg: #4f46e5` / hover `#4338ca` for `6.30:1` WCAG AA contrast with `#ffffff`): Primary action buttons, active navigation rail indicator, active tab pills, and focus rings.

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
- **Secondary & Muted Ink** (`#cbd5e1` / `#94a3b8` in `night`, `#334155` / `#475569` in `winter`): Supporting metadata, timestamps, units, and inactive labels (maintaining ≥ 4.5:1 contrast for body copy).
- **Structural Hairlines** (`var(--v-hairline-subtle)` `rgba(226, 232, 240, 0.07)` subtle, `var(--v-hairline)` `rgba(226, 232, 240, 0.13)` default): 1px cell dividers and container borders.

### Semantic Inks
- **Fiduciary Emerald (Gain / Inflow / On-Pace)** (`#10b981` in `night`, `#047857` in `winter`, tint `rgba(16, 185, 129, 0.12)`): Positive portfolio returns, net savings surplus, refunded credits, and beat-goal months.
- **Ledger Rose (Outflow / Deficit / Alert)** (`#f43f5e` in `night`, `#be123c` in `winter`, tint `rgba(244, 63, 94, 0.12)`): Spend pace overages, negative returns, missed goals, and destructive actions.
- **Caution Amber (Pending / EMI / Partial)** (`#f59e0b` in `night`, `#b45309` in `winter`, tint `rgba(245, 158, 11, 0.12)`): Active EMI commitments, pending statement reconciliations, and partial goal months.

### Named Rules
**The Action-Only Accent Rule.** Sovereign Indigo marks interactive controls and active states. Never tint large hero backgrounds or static metric numbers in primary indigo; primary figures sit in Primary Ink while semantic delta pills carry Emerald or Rose.

**The Single-Hairline Rule.** Adjacent cells in a metric strip or ledger table share a single 1px border (`1px solid var(--v-hairline-subtle)`). Never place a thick colored `border-left` or `border-right` (>1px) on cards, callouts, or list rows.

## Typography

**Display & UI Font:** `Inter` (with `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` fallback)
**Icon System:** `Material Symbols Outlined` (20px default UI size, consistent 400 weight; filled variant on active nav states) and crisp inline SVGs (`templates/includes/vault_icon.html`).

### Hierarchy
- **Display Figure** (`700`, `2.25rem` / `36px`, line-height `1.15`, tracking `-0.03em`, `tabular-nums`): Lead monetary figure inside a page's Ledger Band.
- **Page Headline** (`700`, `1.5rem` / `24px`, line-height `1.25`, tracking `-0.02em`): Route title in `.v-page-header`.
- **Section Title** (`600`, `1rem` / `16px`, line-height `1.35`, tracking `-0.01em`): Direct panel and workbench headings.
- **Body & Table Data** (`400` / `500`, `0.875rem` / `14px`, line-height `1.5`, `tabular-nums` on numbers): Ledger rows, descriptions, and form controls (prose constrained to `65ch`).
- **Column & Cell Label** (`600`, `0.75rem` / `12px`, line-height `1.35`, tracking `0.02em`): Table column headers, stat cell labels, and filter chips.

### Named Rules
**The No-Kicker Rule.** Never place a small uppercase eyebrow or kicker label above a page headline or section title. Let the heading and its inline count or subtitle speak directly.

**The Tabular Lock Rule.** Every element displaying currency (`₹`), percentages (`%`), weights (`g`), land units (`Gaj`, `Bigha`, `Sq.ft`), quantities, or dates MUST apply `font-variant-numeric: tabular-nums`.

## Layout

Vault uses a responsive shell built for wide desktop monitors (`1280px–1600px+`) and one-handed mobile PWA operation (`360px–430px` & `768px`):

- **Desktop Left Navigation Rail (`aside#desktopSidebar`, ≥1024px)**: Fixed `240px` width (collapses smoothly to `64px` centered icon rail). Organized into domain groups (Wealth & Portfolio, Cashflow & Tax, Workspace) with a compact user/role footer and lock indicator.
- **Sticky Utility Topbar (`header.v-topbar`, `56px` height)**: Displays route context on desktop, brand identity on mobile, vault session lock timer when unlocked, quick theme switch, and account menu.
- **Main Stage Container (`max-w-[1440px] mx-auto px-4 lg:px-8`)**: Consistent `24px` vertical rhythm between major zones and `16px` inside workbenches.
- **Page Structure Grammar**:
  1. **Page Header (`.v-page-header`)**: Route title + subtitle on the left; period switcher (FY tabs / Month switcher) and compact `.v-toolbar` on the right.
  2. **Ledger Summary Band (`.v-ledger-band`)**: Full-width ruled container with lead metric + delta badge + `.v-horizon` bar on the left (`5` cols) and a `1px` hairline-divided `.v-stat-grid` of 3–4 KPI cells on the right (`7` cols).
  3. **Primary Workbench (`.v-workbench`)**: Balanced asymmetric 2-column split (`8/4`, `7/5`, or `1/1`) with `align-items: start` and natural panel height (zero dead vertical voids), or segmented tabbed workspace.
- **Mobile Ergonomic Adaptation (`360px–430px` & `768px`, `<1024px`)**:
  - **Bottom Dock + Navigation Sheet**: `aside#desktopSidebar` hides below `1024px` in favor of a 5-slot fixed bottom dock (`nav.dock.v-mobile-dock`: Portfolio, Savings, Spends, Jewellery [or HRA fallback], and `More`) paired with `<dialog id="mobileNavDrawer">` and `env(safe-area-inset-bottom)` clearance.
  - **Touch Targets & Input Clearance**: Interactive controls below `1024px` enforce `>=44x44px` hit targets, `16px` mobile input text (preventing iOS Safari auto-zoom), and guaranteed leading/trailing icon padding clearance inside search and password fields.
  - **Dense Mobile Financial Tables**: Three complementary zero-overflow (`overflow-x: clip`) patterns: `.v-table-wrap.v-table-sticky` (scroll shadows + pinned first column), `.v-table.v-table-stack` (`td[data-label]` card stack `<640px`), and `.v-mobile-row` (`md:hidden` 2-column ledger rows synced with `initPagination()`).
  - **Bottom-Sheet Modals (`<768px`)**: Standard `dialog.modal:not(.v-modal-drawer)` dialogs anchor to the bottom viewport edge (`max-height: 92dvh`, sticky `.v-modal-header`, safe-area `.v-modal-footer`).
  - **Orphan-Free Stat Grids**: `.v-stat-grid` and `.v-stat-strip` span odd trailing cells full width on 2-column mobile/tablet breakpoints.

## Elevation & Depth

Surfaces at rest sit flat on the Folio Ground (`#0b0f17`), separated by luminance steps (`#111722` sheet → `#182030` elevated well) and crisp 1px structural hairlines. Shadows appear strictly on floating overlays:
- **Resting Panel**: `box-shadow: none; border: 1px solid var(--v-hairline-subtle)`.
- **Interactive Lift**: `0 8px 24px -4px rgba(0, 0, 0, 0.35), 0 2px 6px rgba(0, 0, 0, 0.2)` on clickable navigation tiles or popovers.
- **Overlay & Drawer**: `0 24px 48px -12px rgba(0, 0, 0, 0.65), 0 4px 16px rgba(0, 0, 0, 0.35)` over dimmed backdrop (`rgba(5, 8, 15, 0.72)` with `backdrop-filter: blur(6px)`).

**The Flat-At-Rest Rule.** Panels, metric strips, and tables never cast drop shadows at rest and never jump upward (`translateY`) when hovered unless the entire panel is an anchor link.

## Shapes

- **Control & Filter Chip Radius (`8px` / `0.5rem`)**: Buttons, inputs, selects, segmented tab buttons, and `.filter-pill` filter chips use a crisp `8px` radius.
- **Panel & Ledger Band Radius (`12px` / `0.75rem`)**: Primary containers (`.v-ledger-band`, `.v-panel`, `.v-table-wrap`) use a tight `12px` radius with `overflow: hidden`.
- **Drawer & Modal Radius (`16px` / `1rem`)**: Dialog boxes and bottom/side sheets.
- **Status & Delta Pills (`9999px`)**: Compact semantic badges and percentage `.v-delta` pills.

## Components

- **Buttons (`.btn`, `.v-btn`)**: `8px` radius, `36px` toolbar height (`>=44px` on `<1024px`), primary fill `#4f46e5` (hover `#4338ca`) with `#ffffff` text reserved for at most one primary CTA per screen; quiet secondary surface fill (`rgba(226, 232, 240, 0.05)`) for utility actions.
- **Ledger Summary Band (`.v-ledger-band`, `.v-stat-grid`, `.v-stat-cell`)**: Contiguous `12px`-radius `#111722` header with `1px` internal hairlines, Display Figure, `.v-delta` pill, and `.v-horizon` bar.
- **Workbench Panels (`.v-panel`, `.v-panel-header`, `.v-panel-body`)**: Flat `12px` sheet container (`min-width: 0`, respecting explicit `max-w-*` utility constraints on narrow auth/gate cards). Internal subdivisions use `1px` hairlines (`var(--v-hairline-subtle)`) — never nested bordered cards.
- **Data Tables (`.v-table-wrap`, `.v-table`)**: Edge-to-edge inside `.v-panel`, sticky `#182030` header with `11px` uppercase tracked column labels, right-aligned `tabular-nums` numeric columns, and totals footer row.
- **Inputs & Icon Fields (`.v-input`)**: `42px` height (`>=44px` on touch), `8px` radius, Indigo focus ring, and dedicated horizontal clearance whenever paired with leading search icons or inline trailing password-toggle buttons.

## Do's and Don'ts

### Do:
- **Do** open primary dashboards and detail pages with a `.v-ledger-band` (or `.v-stat-strip` on subpages) pairing the lead figure, delta, and `.v-horizon` bar.
- **Do** right-align all monetary amounts, percentages, and weights in tables and ledger rows with `tabular-nums`.
- **Do** group secondary utilities (Sync Sheets, Refresh Prices, Export, Biometrics) in `.v-toolbar` so the primary CTA stands alone.
- **Do** keep 2-column workbenches balanced with zero empty column voids and zero nested card borders.
- **Do** preserve all Django template blocks, URL tags, CSRF tokens, form field names, and JS hooks (`openModal`, `closeModal`, `confirmDelete`, `initPagination`, Chart.js canvas IDs).

### Don't:
- **Don't** nest bordered cards inside `.v-panel` or `.v-ledger-band`; use `1px` hairline-divided rows/cells instead.
- **Don't** place small uppercase kicker/eyebrow labels above `<h1>`, `<h2>`, or `<h3>` headings.
- **Don't** use thick colored left borders (`border-l-4`), gradient text (`bg-clip-text`), or glowing neon placeholder boxes.
- **Don't** use raw emoji as UI icons; use `Material Symbols Outlined` or authored inline SVGs everywhere.
