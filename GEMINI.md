# Antigravity Rules — Vault Personal Finance

These rules guide Google Antigravity agents when operating within this repository.

---

## 1. Code Intelligence & Navigation with CodeGraph

- **CodeGraph is Installed**: The CodeGraph knowledge graph index is initialized in `.codegraph/` (2,200+ nodes, 5,000+ edges) and configured as an MCP server.
- **Query CodeGraph Before Grepping**:
  - To locate symbols, classes, or routes: use `codegraph query <symbol>` or the `codegraph_query` MCP tool.
  - To explore feature subsystems: use `codegraph explore "<topic>"` or `codegraph_explore`.
  - To trace call paths: use `codegraph callers <symbol>` / `codegraph callees <symbol>` or their MCP equivalents.
  - Before modifying function signatures: run `codegraph impact <symbol>` to verify the blast radius.
- **Index Sync**: Run `codegraph sync` after making significant structural code changes.

---

## 2. Secrets & Credential Protection

- **STRICT PROHIBITION**: Never read, dump, print, or commit secrets:
  - Secret files: `.env`, `scripts/DEPLOY.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, `**/google-service-account.json`.
  - Never dump environment variables in terminals or outputs (`printenv`, `env`, `echo $SECRET_KEY`).
  - Never print password hashes, encrypted OAuth tokens, or WebAuthn credentials from the database.
- Reference `.env.example` or `pftracker/settings.py` when discussing configuration settings.

---

## 3. Financial Calculation Standards

- **Decimal Types Only**: Always use Python `Decimal` for currency, interest rates, weights, and holdings. Never use floating-point types for monetary values.
- **Quantization**: Currency and returns must be quantized to 2 decimal places (`.quantize(Decimal('0.01'))`) or integer rupees (`.quantize(Decimal('0'))`).
- **Fiscal Calendar**: Vault uses the Indian Financial Year (April 1 to March 31). Use helpers `fy_start_year()` and `fy_label()` from `pftracker.utils`.

---

## 4. Multi-Tenancy, Roles & Security

- **Multi-Tenancy**: All data is scoped to an `AccountGroup` with toggles configured in `HouseholdConfig`.
- **User Roles**:
  - `PRIMARY`: Full access across all modules, including investments, real estate, and MCP tools.
  - `ACCOUNT_HOLDER`: Access to Savings, Expenses, Jewellery, HRA, and Notes; investments and investment-tagged expenses are masked.
  - `LANDLORD`: View-only access strictly restricted to HRA rent records.
- **Security Gate**: Portfolio and Jewellery are gated behind `_vault_gate`, requiring portfolio password or WebAuthn biometric unlock (30-min TTL).

---

## 5. UI & Design System

- **Design Aesthetic**: Dark-first glassmorphism (`night` theme, `#1a1b26`), Inter font, Material Symbols Outlined icons, DaisyUI 5, and Tailwind CSS.
- **Responsive Layout**: Collapsible sidebar on desktop (`aside#desktopSidebar`), fixed bottom dock navigation on mobile (`nav.dock`).
- **Interactive Feedback**: Always provide CSRF tokens on forms, use modal confirmations (`#confirmDeleteModal`) for destructive deletions, and adapt Chart.js charts dynamically to theme changes.

---

## 6. MCP Architecture & Mutations

- Changes made via MCP must record before/after JSON audit records in `MCPAuditLog` (`mcp_server.audit`) to preserve one-click revert capabilities.
- Starlette ASGI router (`pftracker.asgi`) serves `/mcp` endpoints alongside Django at `/`.

---

## 7. Git Commit & Pre-Push Verification Standards

- **Pre-Push Local Verification (MANDATORY)**: Never commit or push unverified code. Before committing and pushing:
  - Run lint verification locally: `./venv/bin/ruff check --select F,E9 .` (must pass with 0 errors).
  - Run test suite locally: `./venv/bin/python manage.py test --keepdb` (must pass 100%).
  - Synchronize CodeGraph index: `codegraph sync`.
- **Conventional Commits**: Every commit must follow `<type>(<scope>): <summary>` format (`feat`, `fix`, `refactor`, `perf`, `test`, `chore`, `docs`).
- **Comprehensive Body**: Commit messages must never be vague or single-line summaries. Always include a paragraph detailing motivation and a bulleted list of specific changes, additions, and removals.
