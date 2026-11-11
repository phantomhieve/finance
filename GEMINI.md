# GEMINI.md — Antigravity Quick Reference

Concise operational index for Google Antigravity agents in **Vault**. For full architecture and module contracts, read [`AGENTS.md`](AGENTS.md) and [`.agents/skills/vault-architecture/SKILL.md`](.agents/skills/vault-architecture/SKILL.md).

---

## Core Invariants

1. **CodeGraph First ([`.agents/rules/codegraph-navigation.md`](.agents/rules/codegraph-navigation.md))**:
   - Use `codegraph_query`, `codegraph_node`, `codegraph_explore`, `codegraph_callers`, `codegraph_callees`, and `codegraph_impact` (index in `.codegraph/`) before grepping. Run `codegraph sync` after structural changes.
2. **Zero Secret Exposure ([`.agents/rules/no-secrets.md`](.agents/rules/no-secrets.md))**:
   - Never read, print, grep, or commit `.env`, `scripts/DEPLOY.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, or service-account JSONs; never dump env vars (`env`, `printenv`). Reference `.env.example`, `portfolio/investor_profile.md.example`, and `pftracker/settings.py`.
3. **Financial Precision & Indian FY ([`.agents/rules/financial-precision-and-security.md`](.agents/rules/financial-precision-and-security.md))**:
   - Use Python `Decimal` exclusively for money, weights, and rates (`pftracker.utils.pct`, `pnl_pct`).
   - Indian Financial Year runs April 1 – March 31 (`fy_start_year`, `fy_label` in `pftracker.utils`).
   - Format INR with `{% load indian_format %}` (`|inr`, `|inr_short`, `|indian_number` from `portfolio/templatetags/indian_format.py`) and enforce `tabular-nums`.
4. **Multi-Tenancy & Role Gates ([`AGENTS.md`](AGENTS.md))**:
   - Scope every query to `AccountGroup` (`_gf(group)` fail-closed). Enforce `PRIMARY`, `ACCOUNT_HOLDER` (`_hides_investments` masks `Investments` expenses; no portfolio/MCP access), and `LANDLORD` (`/hra/` read-only).
   - Keep Portfolio & Jewellery behind `_vault_gate` (`30m` TTL) and WebAuthn/password rate limits; enforce `@require_POST` + CSRF on all mutations.
5. **Private Bank Folio UI ([`DESIGN.md`](DESIGN.md), [`.agents/rules/ui-and-design-system.md`](.agents/rules/ui-and-design-system.md))**:
   - Dark-first Private Bank Consolidated Statement aesthetic (`night` `#0b0f17` ground / `#111722` sheet; `winter` `#f8fafc` ground / `#ffffff` sheet) built on Tailwind CSS v4 (`@tailwindcss/browser@4`), DaisyUI 5, Inter, Material Symbols Outlined, and `static/css/style.css`.
   - Use `.v-ledger-band`, `.v-horizon`, `.v-workbench`, and `.v-panel` (zero nested cards, zero eyebrow kickers, `>=44px` touch targets on `<1024px`, desktop `aside#desktopSidebar` + `header.v-topbar`, mobile `nav.v-mobile-dock` + `#mobileNavDrawer`).
6. **AI Gateway, Carbon Tiering & MCP ([`docs/ux/0001-ai-calling-and-dag-strategy.md`](docs/ux/0001-ai-calling-and-dag-strategy.md))**:
   - Route all AI calls through `pftracker/ai_gateway/`: `gemini-4-carbon` (`ThinkingLevel.HIGH` in prod) for portfolio strategy/synthesis & land appraisal; `gemini-3.8-flash` (`thinking_budget=0` in prod) for Stage 1 specialist lenses and expense operations.
   - Pre-compute `Decimal` metrics in Python before prompting, use `DjangoSafeThreadPoolExecutor` for thread concurrency, and log every MCP write via `MCPAuditLog` (`mcp_server/audit.py`).
7. **Verification & Git ([`.agents/rules/git-commits.md`](.agents/rules/git-commits.md))**:
   - Run `./venv/bin/ruff check --select F,E9 .`, `./venv/bin/python manage.py check --fail-level WARNING`, `./venv/bin/python manage.py test --keepdb`, and `codegraph sync` before committing with descriptive Conventional Commits.
