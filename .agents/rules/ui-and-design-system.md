# UI & Design System Rules

1. **Theme & Aesthetics**:
   - Default theme is `night` (dark glassmorphism, base color `#1a1b26`). Light theme is secondary (`#e2e8f2`).
   - Use DaisyUI 5 utility classes paired with Tailwind CSS browser compiler.
   - Typography: Google Font 'Inter' (`font-sans`), with Material Symbols Outlined (`material-symbols-outlined`) for all icons.
   - Gradients: Use the predefined brand linear gradients (`brand-text`, `card-glass`, `vault-icon-wrap`).

2. **Responsive Layout Structure**:
   - Mobile: Fixed bottom dock (`<nav class="dock">`) with direct touch navigation to Savings, Spends, Portfolio, Jewellery, HRA, Notes, and Back.
   - Desktop: Collapsible left sidebar (`aside#desktopSidebar`) with sticky top navbar (`header.navbar-glass`).
   - Content area: Full height with sticky page header block (`{% block page_header %}`) and main content block (`{% block content %}`).

3. **Chart Visualizations**:
   - Charts use Chart.js 4.4 loaded via CDN.
   - Charts must adapt dynamically to theme changes (`night` vs `light`), using semi-transparent glass fills and rounded bar corners.

4. **Interactive Safety**:
   - All destructive actions (deleting transactions, expenses, holdings, goals) MUST use POST forms with CSRF tokens and trigger the standard modal dialog (`#confirmDeleteModal`).
