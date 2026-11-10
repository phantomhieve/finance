---
version: 1
slug: "templates-base-html"
primary_target: "templates/base.html"
related_targets: ["templates/portfolio/master.html","templates/expenses/home.html","templates/tracker/dashboard.html","templates/jewellery/dashboard.html"]
---

# Surface Brief — Vault Application Shell & Shared System

## Scope & Mode
- **Primary Target**: `templates/base.html` (and shared system in `static/css/style.css`, `static/js/charts.js`)
- **Mode**: `operate`

## Audience & Job
- Indian household controllers (`PRIMARY`), partners (`ACCOUNT_HOLDER`), and landlords (`LANDLORD`) operating a private multi-asset balance sheet, April–March FY savings ledger, automated bank/card expense audit, and physical locker inventory.
- Need immediate legibility of net worth, pace deltas, and exceptions without wading through generic dashboard card soup.

## Direction contract

THESIS: Vault replaces generic glassmorphic card grids with the Private Bank Statement & Family Office Ledger — a ruled, high-density fiduciary folio where a full-width top ledger band and proportional horizon bar establish immediate net-worth and cashflow posture, and asymmetric workbenches separate high-volume tabular data from contextual controls and progressive drawers.

OWN-WORLD: Deep obsidian folio slate (`#0b0f17`) with elevated ledger sheet surfaces (`#111722` and `#182030`), crisp 1px hairlines (`rgba(226, 232, 240, 0.08)`), sovereign indigo action ink (`#6366f1`), emerald gain ink (`#10b981`), rose outflow ink (`#f43f5e`), and bullion gold (`#eab308`). Strictly tabular numerals (`tabular-nums`) across all `₹` Lakh/Crore figures, weights, and dates; zero eyebrow kickers, zero nested cards, and zero decorative gradients.

STORY: The operator opens any route and reads the primary fiduciary position, period delta, and proporcional allocation/pace bar within two seconds in the Ledger Band, then scans or acts in a structured 2-column workbench or ruled ledger table while secondary detail (AI briefs, reconciliation logs, add/edit forms) opens cleanly on demand.

FIRST VIEWPORT: Fixed left collapsible navigation rail (`248px` / `68px` on desktop, ergonomic bottom dock on mobile) + `56px` utility topbar with breadcrumb/route context, quick command/filter slot, theme switch, and role badge. Below the header sits the Page Header bar (title + primary action toolbar) and the full-width Ledger Summary Band (`vault-ledger-band`) housing the primary figure, period delta pill, proportional horizon strip (`vault-horizon-bar`), and 3–4 ruled stat cells, followed immediately by the primary workbench.

FORM: Candidate 5 (Private Bank Consolidated Portfolio Statement & Family Office Folio) from the grounded cultural list; `seed:268352c73ba6ff17`. Raised by declined challengers: zero-gap ruled cell density (`pop-culture-shelf-doujin-event-catalog`), immutable strike/void audit trail (`vernacular-ephemera-jet-age-ticket-wallet`), action-only primary saturation (`digital-design-canon-warm-consumer-app-surface`), contour pace reference lines (`notation-diagram-systems-orienteering-map`), colour-coded multi-segment horizon bar (`wayfinding-cartography-signage-midnight-transit-diagram`), and pinned tabular column discipline (`signals-instruments-split-flap-concourse`).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
