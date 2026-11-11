# UI & Design System Rules

Authoritative references: [`DESIGN.md`](../../DESIGN.md), [`docs/ux/IA.md`](../../docs/ux/IA.md), and [`docs/ux/components.md`](../../docs/ux/components.md).

1. **Private Bank Folio Aesthetic & Themes**:
   - Default theme is `night` (Folio Ground `#0b0f17`, Ledger Sheet `#111722`, Elevated `#182030`); light theme is `winter` (`#f8fafc` ground, `#ffffff` sheet), persisted in `localStorage` under `vault-theme`.
   - Styling runs on Tailwind CSS v4 (`@tailwindcss/browser@4`), DaisyUI 5, and `static/css/style.css` (`public.css` for public routes, `admin_theme.css` + Unfold for `/vault-manage/`).
   - Typography uses `Inter` (`font-sans`) with `Material Symbols Outlined` icons (or crisp inline SVGs; never raw emoji). Every currency figure, weight, percentage, quantity, and date MUST enforce `font-variant-numeric: tabular-nums`.
   - Sovereign Indigo (`#6366f1`, primary button fill `#4f46e5` / hover `#4338ca` for WCAG AA contrast) is reserved strictly for interactive actions, active route markers, and focus rings — never decorative text gradients, thick left borders (`border-l-4`), or hero tints.

2. **Page Structure & Anti-Clutter Invariants**:
   - Open dashboards and detail views with a hairline-ruled `.v-ledger-band` (including a proportional `.v-horizon` bar) or `.v-stat-strip`.
   - Organize workspaces into balanced asymmetric workbenches (`.v-workbench`) or segmented folios (`.v-segmented`).
   - **Zero Nested Cards**: Never place bordered cards inside a `.v-panel`; separate internal sections with `1px` structural hairlines (`var(--v-hairline-subtle)` / `.v-divide-list`).
   - **No Eyebrow Kickers**: Never place tiny uppercase kicker labels above `<h1>`, `<h2>`, or `<h3>` headings.

3. **Responsive & Mobile Shell (`360px–430px`, `768px`, `1024px+`)**:
   - Desktop (`lg+`): Collapsible left rail (`aside#desktopSidebar`) + sticky utility topbar (`header.v-topbar`).
   - Mobile (`<lg`): Fixed 5-slot bottom dock (`nav.v-mobile-dock`) + `<dialog id="mobileNavDrawer">` with `env(safe-area-inset-bottom)` clearance, bottom-sheet modals (`<768px`), `>=44x44px` touch targets, `16px` mobile inputs (no iOS auto-zoom), and zero horizontal overflow (`overflow-x: clip`).

4. **Charts & Interactive Safety**:
   - Subscribe Chart.js views (`charts.js`, `expenses.js`) to the `vault:themechange` event so axes, gridlines, and tooltips adapt live between `night` and `winter`.
   - Keep all destructive mutations on CSRF-protected POST forms gated by `#confirmDeleteModal` (`confirmDelete()`).
