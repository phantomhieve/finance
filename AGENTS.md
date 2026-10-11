# AGENTS.md — Antigravity Agent Guidelines

See [GEMINI.md](file:///Users/phantomhive/Desktop/Atul/finance/GEMINI.md) for full system specifications.

## Quick Reference for Antigravity Agents

1. **CodeGraph Tools Available**:
   - The repository knowledge graph is built in `.codegraph/`.
   - Prefer querying CodeGraph (`codegraph_query`, `codegraph_node`, `codegraph_callers`, `codegraph_explore`) over broad regex searches.
   - Run `codegraph sync` after creating or moving modules.

2. **Security & Secrets**:
   - Never inspect or dump `.env`, `.deploy-keys/`, credentials, or database hashes.
   - Always verify role permissions (`can_view_portfolio`, `_vault_gate`) when touching portfolio or jewellery views.

3. **Financial Precision**:
   - Use `Decimal` exclusively for currency, investments, and commodity weights.
   - Respect Indian FY (April–March) logic from `pftracker.utils`.

4. **UI & Theme**:
   - Maintain DaisyUI 5 + Tailwind glassmorphism dark-mode aesthetic (`night` theme).
   - Ensure responsive design with desktop sidebar and mobile bottom dock.

5. **Git Commit Standards**:
   - Always write structured Conventional Commits (`type(scope): summary`).
   - Always provide a detailed commit body describing *why* the change was made and a bulleted breakdown of modified components. Never use vague one-liners.

