# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary Household Controller (`PRIMARY`)**: An Indian working professional or household head managing a multi-asset family balance sheet (Indian equities via Zerodha, mutual funds, US RSUs, EPF/PPF/NPS, fixed deposits, sovereign & corporate bonds, physical gold/silver bullion, locker and safe jewellery, and agricultural/residential real estate measured in Gaj/Bigha/Sq.ft). Reviews portfolio allocation, cashflow pacing, credit card statement reconciliations, and tax-saving targets across desktop and mobile PWA viewports.
- **Household Partner / Family Member (`ACCOUNT_HOLDER`)**: Co-manages household cashflow, day-to-day credit card and UPI spends, shared financial notes, and HRA rent receipts, with read-only access to monthly savings goals and the physical jewellery catalog (valuations and jewellery CRUD restricted to `PRIMARY`). Investment holdings and investment-tagged outflows remain masked (`_hides_investments`).
- **Landlord (`LANDLORD`)**: Restricted, view-only external role that signs in exclusively to verify HRA rent transfers and payment history.

## Product Purpose

Vault is a private, self-hosted household wealth intelligence and personal finance operating system tailored for the Indian fiscal and banking ecosystem. It consolidates scattered spreadsheets, broker portals, bank alert emails, and physical locker lists into one role-aware ledger so every rupee of net worth, every monthly savings target across the April–March Indian Financial Year, every credit card bill reconciliation, and every gram of gold in the bank locker is legible in seconds.

## Positioning

Vault unifies automated Indian banking ingestion (parsing 30+ Indian bank alert emails and unlocking password-protected credit card PDF statements for 3-stage reconciliation), Indian fiscal mechanics (April–March FY pacing, HRA rent tracking, Lakh/Crore `₹` notation, 24K/22K fineness-adjusted live bullion & jewellery valuation, and regional land unit appraisals in Gaj/Bigha), household role-based masking (`PRIMARY` vs. `ACCOUNT_HOLDER` vs. `LANDLORD`), and quant-grounded multi-stage AI financial auditing in a single private deployment.

## Operating Context

- **Daily / Weekly Cashflow & Spend Triage**: Gmail OAuth 2.0 background sync ingests credit card and UPI bank alerts; users review daily spend pace against the prior month, inspect flagged anomalies or unlinked refunds, and categorize transactions.
- **Monthly Credit Card Statement Reconciliation**: When monthly PDF statements arrive via email, Vault unlocks them and runs 3-stage reconciliation (matching alert rows, importing missed lines, and tracking active EMI amortizations and bill due dates).
- **Monthly & Annual Indian FY Savings Pacing**: Tracks net savings, extra income, and inter-account transfers from April 1 to March 31 against base monthly goals, mid-year salary increments, and single-month goal adjustments.
- **Multi-Asset Portfolio & Vault Review**: Gated behind a 30-minute session lock (`_vault_gate` via password or WebAuthn passkey). Connects to Google Sheets and live market/metal price fetchers to track 11 asset classes, Child Portfolio ring-fencing, financial goal funding roadmaps, and AI-driven portfolio & land appraisal briefs.
- **Physical Jewellery & Locker Audit**: Catalogues family ornaments by metal (Gold, Silver, Platinum, Diamond), purity/fineness, gross/net weight in grams, and physical custody (`BANK_LOCKER` vs. `HOME_SAFE`) with live bullion valuation and photo proof.

## Capabilities and Constraints

- **Stack & Architecture**: Django 6.0 server-rendered templates with Tailwind CSS v4 (`@tailwindcss/browser@4`), DaisyUI 5 (`night` default dark theme, `winter` light theme), Unfold Admin (`/vault-manage/`), Chart.js 4, Material Symbols Outlined icons, and vanilla JS modules (`vault-core.js`, `vault-utils.js`, `charts.js`, `expenses.js`, `jewellery.js`, `nps_modal.js`, `commodity_purity.js`, `sortable.js`).
- **Financial & Fiscal Precision**: Strictly `Decimal` arithmetic on the backend; Indian numbering system (`₹12,50,000`, `₹1.25 L`, `₹3.40 Cr`) via `indian_format` template tags (`inr`, `inr_short`, `indian_number`); April–March Financial Year (`FY 2026-27`).
- **Strict Template Contract**: Every Django template block (`title`, `extra_head`, `page_header`, `content`, `login_content`, `chart_js`, `extra_js`), URL name, context variable, CSRF token, form field name, `<dialog>` modal ID, and JS hook remains intact.
- **Navigation Topology**: Desktop collapsible left sidebar (`aside#desktopSidebar`) + sticky topbar (`header.v-topbar`), and mobile fixed 5-slot bottom dock (`nav.v-mobile-dock`) + navigation sheet (`#mobileNavDrawer`).

## Brand Commitments

- **Name**: Vault
- **Theme Commitment**: Dark-first (`night` theme default with `winter` daylight toggle), desktop sidebar + mobile bottom dock.
- **Visual Identity**: Institutional-grade Private Bank Consolidated Statement & Family Office Folio — ruled structural hairlines, crisp hierarchy, and zero card clutter.

## Evidence on Hand

- Production Django models, views, template tags (`indian_format.py`), and HTML templates across `portfolio/`, `expenses/`, `tracker/`, `jewellery/`, `public/`, `admin/`, and `unfold/`.
- Authored inline SVG vault emblem (`templates/includes/vault_icon.html`) and PWA icons (`static/icons/`).
- Invite-only private household deployment; product surfaces never fabricate commercial pricing or external customer testimonials.

## Product Principles

1. **Ledger Authority Over Dashboard Clutter**: Every screen reads like an institutional family-office statement — clear primary figures, immediate delta context, structured tabular comparisons, and zero decorative card bloat.
2. **Progressive Disclosure of Complexity**: Lead with the decisive number and pace status in the first viewport; place secondary breakdowns, raw reconciliation logs, AI methodology notes, and infrequent admin actions inside clean disclosures, drawers, or tabs.
3. **Indian Fiscal Native**: Treat Lakhs/Crores scannability, April–March FY rhythms, 24K/22K gram purity math, and Indian banking workflows (UPI, credit card statement PDFs, EMIs, EPF/NPS, HRA rent) as first-class primitives.
4. **Role-Safe & Tactile Speed**: Navigation, filters, and modal entry flows operate at keyboard and thumb speed, preserving scroll position across POST redirects and enforcing `PRIMARY`, `ACCOUNT_HOLDER`, and `LANDLORD` boundaries.

## Accessibility & Inclusion

- WCAG AA contrast compliance across both `night` and `winter` themes (body text ≥ 4.5:1, large headings/figures ≥ 3:1, primary CTA button fill `#4f46e5` at 6.30:1 with `#ffffff`).
- Strict `font-variant-numeric: tabular-nums` on every monetary value, weight, percentage, date, and counter so vertical columns align cleanly.
- Full keyboard navigation (`:focus-visible` rings, native `<dialog>` Escape/backdrop handling), `>=44x44px` touch targets on `<1024px`, and `prefers-reduced-motion: reduce` support.
