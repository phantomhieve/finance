---
name: Vault Design System
description: Precision financial intelligence and wealth management interface engineered for the Indian ecosystem
colors:
  primary: "#6366f1"
  primary-hover: "#4f46e5"
  primary-focus: "rgba(99, 102, 241, 0.25)"
  secondary: "#06b6d4"
  secondary-hover: "#0891b2"
  accent: "#8b5cf6"
  neutral-bg: "#0d1117"
  surface-1: "#161b22"
  surface-2: "#21262d"
  surface-3: "#30363d"
  surface-glass: "rgba(22, 27, 34, 0.75)"
  text-primary: "#f0f6fc"
  text-secondary: "#8b949e"
  text-muted: "#6e7681"
  border-subtle: "rgba(240, 246, 252, 0.08)"
  border-default: "rgba(240, 246, 252, 0.14)"
  border-focus: "#6366f1"
  positive: "#10b981"
  positive-subtle: "rgba(16, 185, 129, 0.12)"
  negative: "#f43f5e"
  negative-subtle: "rgba(244, 63, 94, 0.12)"
  warning: "#f59e0b"
  warning-subtle: "rgba(245, 158, 11, 0.12)"
  gold: "#eab308"
  silver: "#94a3b8"
typography:
  display:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  title:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  caption:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.01em"
  icons:
    fontFamily: "'Material Symbols Outlined'"
  ramp:
    nano: "9px"
    micro: "10px"
    xs: "11px"
    caption: "12px"
    search: "17px"
    sm: "0.75rem"
    base: "0.875rem"
    md: "1rem"
    lg: "1.125rem"
    icon: "20px"
    xl: "1.25rem"
    xxl: "1.5rem"
    display: "2rem"
    hero: "2.5rem"
  numeric:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontVariantNumeric: "tabular-nums"
rounded:
  none: "0px"
  xs: "4px"
  sm: "6px"
  md: "8px"
  base: "10px"
  lg: "12px"
  card: "14px"
  xl: "16px"
  modal: "20px"
  2xl: "24px"
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
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  card-surface:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "20px"
---

# Vault Design System

## Overview
Vault is an Indian personal finance, wealth intelligence, and multi-asset portfolio platform. Designed under the **Operate** mode of the Impeccable craft standard, it prioritizes precision, high information density, rapid scanning, and uncompromised financial legibility.

The interface adheres to an architectural, refined glassmorphic dark theme ("night" mode) as its primary persona, supported by a crisp daylight theme ("winter" mode). The aesthetic is calm, authoritative, and fiduciary:
- Zero decorative distractions or artificial hype.
- Tonal hierarchy over neon borders.
- Absolute data integrity with strict tabular numeric alignment across all currencies, rates, units, and timestamps.
- Native Indian financial formatting (₹ Lakhs, Crores, 24K/22K Gold per gram, Gaj/Bigha land measurements, April–March Fiscal Year).

## Colors
The color system operates on semantic roles with strict contrast compliance (body text >= 4.5:1, large headings >= 3:1 against their ground).

### Night Palette (Default Ground)
- **Base Ground (`#0d1117`)**: Deep obsidian dark, calibrated for minimal glare and maximum focus during extended analytical sessions.
- **Surface Layer 1 (`#161b22`)**: The foundational card and sidebar surface with 1px border highlight `rgba(240, 246, 252, 0.08)`.
- **Surface Layer 2 (`#21262d`)**: Elevated containers, table header rows, input backgrounds, and modal cards.
- **Surface Layer 3 (`#30363d`)**: Hover states, active tabs, and divider structures.
- **Surface Glass (`rgba(22, 27, 34, 0.75)`)**: Used exclusively for sticky headers and navigation bars with `backdrop-filter: blur(16px)`.

### Accent & Semantic Tokens
- **Primary Indigo (`#6366f1` / `#818cf8`)**: Primary brand actions, active state markers, focused inputs.
- **Positive / Inflow / Gains (`#10b981` / `#34d399`)**: Net savings, portfolio returns, asset gains, positive cashflows. Paired with subtle translucent fill `rgba(16, 185, 129, 0.12)`.
- **Negative / Outflow / Loss (`#f43f5e` / `#fb7185`)**: Spends, liabilities, market dips, critical anomalies. Paired with subtle translucent fill `rgba(244, 63, 94, 0.12)`.
- **Warning / Pending / EMI (`#f59e0b` / `#fbbf24`)**: Pending reconciliations, upcoming EMIs, budget thresholds.
- **Precious Metals (`#eab308` Gold, `#94a3b8` Silver, `#38bdf8` Platinum)**: Specialized commodity valuation cards.

### Winter Palette (Light Ground)
- **Base Ground (`#f8fafc`)**: Crisp slate-tinted canvas.
- **Surface Layer 1 (`#ffffff`)**: Clean white container cards with delicate shadow layers.
- **Surface Layer 2 (`#f1f5f9`)**: Input fields, muted pills, subtle table zebra stripes.
- **Text Tokens**: High contrast charcoal (`#0f172a` primary, `#475569` secondary, `#94a3b8` muted).

## Typography
Typography is anchored on **Inter** (display, body, and tabular numbers).

- **Tabular Figures**: Every numeric value (currency amounts, percentages, quantities, dates, times) MUST enforce `font-variant-numeric: tabular-nums` to guarantee vertical column alignment across rows.
- **Scale and Rhythms**:
  - Page Titles: `1.5rem` (24px) / `font-semibold` / tracking `-0.02em`
  - Section Headings: `1.125rem` (18px) / `font-semibold` / tracking `-0.01em`
  - Group Headers: `0.75rem` (12px) / `font-medium` / uppercase / tracking `0.05em`
  - Body Text: `0.875rem` (14px) / `font-normal` / line-height `1.5`
  - Metric Values: `1.25rem` to `2rem` / `font-bold` / tabular-nums
  - Helper & Meta Text: `0.75rem` (12px) / `font-medium` / text-secondary
- **Clean Headings**: Never prepend an artificial kicker or eyebrow label above a heading. Headings speak for themselves. Solid, crisp typography without text-gradient clips.

## Layout
The layout provides seamless transition between expansive desktop viewports and touch-first mobile interfaces:

### Desktop (>= 1024px)
- **Collapsible Fixed Left Sidebar (256px wide, collapses to 68px)**: Fast access to Savings, Expenses, Portfolio, Jewellery, HRA, Notes, and Admin.
- **Top Utility Header (56px fixed)**: Sticky glass bar containing quick search, theme switch, household notifications, and user avatar menu.
- **Main Content Stage**: Padded content area with max-width containment (`max-w-7xl`), organized in structured 12-column responsive CSS grids.

### Mobile (< 1024px)
- **Fixed Ergonomic Bottom Dock (64px + safe-area-inset-bottom)**: High touch-target icons for the 5 primary routes (Savings, Spends, Portfolio, Jewellery, HRA) with immediate active feedback.
- **Adaptive Data Views**: Tables collapse gracefully into high-density card units (`.table-card`) maintaining column semantics without awkward horizontal overflow.

## Elevation & Depth
Elevation is constructed through subtle luminosity shifts, delicate border hair-lines, and multi-layered soft drop shadows.

- **Level 0 (Flat)**: Background ground canvas `#0d1117`.
- **Level 1 (Card Base)**: `box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2), 0 1px 2px rgba(0, 0, 0, 0.12); border: 1px solid rgba(240, 246, 252, 0.08)`.
- **Level 2 (Hover & Popover)**: `box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.35), 0 2px 6px rgba(0, 0, 0, 0.2); border: 1px solid rgba(240, 246, 252, 0.14)`.
- **Level 3 (Modal Dialog & Floating Dropdowns)**: `box-shadow: 0 20px 40px -8px rgba(0, 0, 0, 0.5), 0 4px 12px rgba(0, 0, 0, 0.3); border: 1px solid rgba(240, 246, 252, 0.18)`.
- **Glassmorphic Atmosphere**: `backdrop-filter: blur(16px) saturate(1.4)`. Used selectively on navigation bars and floating overlays to let content underneath provide visual depth without sacrificing legibility.

## Shapes
- **Radius Scale**:
  - Buttons, inputs, chips: `10px` (`rounded-md` / `rounded-lg`)
  - Cards, content sections: `14px` (`rounded-xl`)
  - Dialog modals, sheets: `20px` (`rounded-2xl`)
  - Status badges, avatar badges: `9999px` (`rounded-full`)
- **Interactive States**:
  - Smooth deceleration curves: `transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1)`
  - Active press feedback: `transform: scale(0.98)` on button clicks
  - Focus rings: `outline: 2px solid var(--color-primary); outline-offset: 2px;`

## Components

### 1. Metric Stat Ribbon
High-density financial summary blocks featuring:
- Label (subtle, 12px uppercase medium)
- Formatted Currency (bold, tabular-nums, colored according to positive/negative state)
- Subtext / Period Delta (11px, with clear arrow indicators `↑` / `↓` and delta percentages)

### 2. Financial Data Tables
- Sticky headers with `surface-2` ground and subtle bottom border.
- Hoverable rows with 150ms ease-out transitions.
- Currency and percentage columns right-aligned with `tabular-nums`.
- Actions column with compact icon buttons and tooltips.

### 3. Glassmorphic Modal Dialogs
- Backdrop overlay: `rgba(0, 0, 0, 0.65)` with `backdrop-filter: blur(4px)`.
- Dialog card: `surface-1` background, 1px perimeter border, rounded-2xl corners.
- Clearly separated header, body, and action footer.
- Keyboard accessible: Esc closes, Tab loops within modal focus boundaries.

### 4. Interactive Charts
- Chart.js instances themed to night/winter palette.
- Thin grid lines: `rgba(240, 246, 252, 0.06)`.
- Tooltips: Custom HTML or glass-styled tooltips displaying exact INR numbers and dates.

### 5. Badges & Chips
- Status chips (e.g. `Reconciled`, `Manual`, `Auto-Add`, `Pending`, `Synced`) with 12px text, 4px-8px padding, pill-rounded, with translucent colored background and solid crisp text.

## Do's and Don'ts

### Do
- Do enforce `font-variant-numeric: tabular-nums` on every single number, price, date, and ticker.
- Do use exponential deceleration (`cubic-bezier(0.16, 1, 0.3, 1)`) for micro-interactions and transitions.
- Do maintain accessible contrast ratios (at least 4.5:1 for body and 3:1 for large text).
- Do test keyboard focus visibility across all buttons, inputs, links, and modal triggers.
- Do preserve every Django template tag, CSRF token, form field ID, and dynamic JavaScript/HTMX binding.
- Do style browser primitives: `::selection`, `caret-color`, custom scrollbars, and focus rings.

### Don't
- Don't use 3px/4px thick colored borders on card sides (`border-left: 3px solid ...`). Use tonal fills or clean status badges instead.
- Don't use text gradient clips or transparent text fills. Text must be solid, high-contrast, and legible.
- Don't use bounce or elastic animation easing (`cubic-bezier(0.34, 1.56, ...)`).
- Don't prepend artificial kickers or eyebrows (e.g. "OVERVIEW // METRICS") above headings.
- Don't flood text with em-dashes.
- Don't hardcode fixed widths on containers that break responsiveness on mobile viewports.
- Don't use monospace fonts as a costume for "technical" feel; use monospace only for code, hashes, or technical IDs.
