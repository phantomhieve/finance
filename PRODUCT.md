# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary Household Controller (`PRIMARY`)**: An Indian working professional or household head managing a complex, multi-asset family balance sheet (Indian equities via Zerodha, mutual funds, US RSUs, EPF/PPF/NPS, fixed deposits, sovereign & corporate bonds, physical gold/silver bullion, locker and safe jewellery, and agricultural/residential real estate measured in Gaj/Bigha/Sq.ft). Frequently reviews portfolio allocation, cashflow pacing, credit card statement reconciliations, and tax-saving targets in the evening on desktop or on the go via mobile PWA.
- **Household Partner / Family Member (`ACCOUNT_HOLDER`)**: Co-manages household cashflow, monthly savings goals, day-to-day credit card and UPI spends, physical jewellery inventory, shared financial notes, and HRA rent receipts. Investment holdings and investment-tagged outflows are masked for privacy and role separation.
- **Landlord (`LANDLORD`)**: Restricted, view-only external role that logs in strictly to verify HRA rent transfers and payment history.
- *(Note: Inferred from codebase models, role gates in `tracker/models.py`, and explicit user brief).*

## Product Purpose

Vault is a private, self-hosted household wealth intelligence and personal finance operating system tailored specifically for the Indian fiscal and banking ecosystem. It exists so a single household can replace scattered spreadsheets, broker portals, bank alert emails, and physical locker lists with one authoritative, role-aware ledger. Success means every rupee of net worth, every monthly savings target across the April–March Indian Financial Year, every credit card bill reconciliation, and every gram of gold in the bank locker is legible in seconds without manual drudgery.

## Positioning

Unlike generic consumer budgeting apps or single-broker dashboards, Vault unifies automated Indian banking ingestion (parsing 30+ Indian bank alert emails and unlocking password-protected credit card PDF statements for 3-stage reconciliation), Indian fiscal mechanics (April–March FY pacing, HRA rent tracking, Lakh/Crore `₹` notation, 24K/22K fineness-adjusted live bullion & jewellery valuation, and regional land unit appraisals in Gaj/Bigha), household role-based masking (`PRIMARY` vs `ACCOUNT_HOLDER` vs `LANDLORD`), and multi-stage AI financial auditing in a single private deployment.

## Operating Context

- **Daily / Weekly Cashflow & Spend Triage**: Gmail OAuth 2.0 background sync ingests credit card and UPI bank alerts; users review daily spend pace against the previous month, inspect flagged anomalies or unlinked refunds, and categorize transactions.
- **Monthly Credit Card Statement Reconciliation**: When monthly PDF statements arrive via email, Vault unlocks them and runs a 3-stage reconciliation (matching alert rows, importing missed lines, and tracking active EMI amortizations and bill due dates).
- **Monthly & Annual Indian FY Savings Pacing**: Tracking net savings, extra income, and inter-account transfers from April 1 to March 31 against base monthly goals, mid-year salary increments, and one-off goal adjustments.
- **Multi-Asset Portfolio & Vault Review**: Gated behind a 30-minute session lock (`_vault_gate` via password or WebAuthn passkey). Connects to Google Sheets and live market/metal price scrapers to track 11 asset classes, Child Portfolio ring-fencing, financial goal funding roadmaps, and AI-driven portfolio & land appraisal briefs.
- **Physical Jewellery & Locker Audit**: Cataloguing family ornaments by metal (Gold, Silver, Platinum, Diamond), purity/fineness, gross/net weight in grams, and physical custody (`BANK_LOCKER` vs `HOME_SAFE`) with live scrap/intrinsic valuation and photo proof.

## Capabilities and Constraints

- **Stack & Architecture**: Django 6.0 server-rendered templates with Tailwind CSS v4 (`@tailwindcss/browser@4`), DaisyUI 5 (`night` default dark theme, `winter` light theme), Chart.js 4, Material Symbols Outlined icons, and vanilla JS modules (`vault-core.js`, `vault-utils.js`, `charts.js`, `expenses.js`, `jewellery.js`, `sortable.js`).
- **Financial & Fiscal Precision**: Strictly `Decimal` arithmetic on the backend; Indian numbering system (`₹12,50,000`, `₹1.25L`, `₹3.40Cr`) via `indian_format` template tags (`inr`, `inr_short`, `indian_comma`); April–March Financial Year (`FY 2025-26`).
- **Strict Template Contract**: Every Django template block (`title`, `extra_head`, `page_header`, `content`, `login_content`, `chart_js`, `extra_js`), URL name, context variable, CSRF token, form field name, `<dialog>` modal ID, and JS hook must remain 100% intact.
- **Navigation Topology**: Desktop collapsible left sidebar (`aside#desktopSidebar`) + Mobile ergonomic bottom dock (`nav.dock`).

## Brand Commitments

- **Name**: Vault
- **Theme Commitment**: Dark-first (`night` theme default with `winter` daylight toggle), desktop sidebar + mobile bottom dock.
- **Aesthetic Mandate**: Deep structural redesign of page information architecture and component hierarchy — not a mere color/token reskin. Must feel like a high-precision, institutional-grade private wealth terminal and family office ledger.

## Evidence on Hand

- Production Django models, views, template tags (`indian_format.py`), and 38 HTML templates across `portfolio/`, `expenses/`, `tracker/`, `jewellery/`, `public/`, and `admin/`.
- Existing custom SVG vault emblem (`templates/includes/vault_icon.html`) and PWA icons (`static/icons/`).
- No external marketing testimonials or multi-tenant commercial pricing exist (invite-only private household deployment); future work must never fabricate commercial claims or fake customer quotes.

## Product Principles

1. **Ledger Authority Over Dashboard Clutter**: Every screen must read like an institutional family-office statement — clear primary figures, immediate delta context, structured tabular comparisons, and zero decorative card bloat.
2. **Progressive Disclosure of Complexity**: Lead with the decisive number and pace status in the first viewport; tuck secondary breakdowns, raw reconciliation logs, AI methodology notes, and редкие admin actions behind clean drawers, tabs, or disclosures.
3. **Indian Fiscal Native**: Respect Lakhs/Crores scannability, April–March FY rhythms, 24K/22K gram purity math, and Indian banking realities (UPI, credit card statement PDFs, EMIs, EPF/NPS, HRA rent) as first-class citizens.
4. **Role-Safe & Tactile Speed**: Navigation, filters, and inline/modal entry flows must operate with keyboard and thumb speed, preserving scroll position across POST redirects and respecting `PRIMARY` vs `ACCOUNT_HOLDER` boundaries.

## Accessibility & Inclusion

- WCAG AA contrast compliance across both `night` and `winter` themes (body text ≥ 4.5:1, large headings/figures ≥ 3:1).
- Strict `font-variant-numeric: tabular-nums` on every monetary value, weight, percentage, date, and counter so vertical columns align effortlessly.
- Full keyboard navigation (`:focus-visible` rings, native `<dialog>` Escape/backdrop handling) and `prefers-reduced-motion: reduce` support.
