# AGENTS.md — Antigravity Agent Guidelines

See [GEMINI.md](GEMINI.md) and [.agents/skills/vault-architecture/SKILL.md](.agents/skills/vault-architecture/SKILL.md) for full system specifications.

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

5. **Local Pre-Push Verification (MANDATORY)**:
   - Always test locally before committing or pushing code:
     1. Run lint check: `./venv/bin/ruff check --select F,E9 .` (must pass with 0 errors).
     2. Run test suite: `./venv/bin/python manage.py test --keepdb` (must pass 100%).
     3. Run CodeGraph sync: `codegraph sync`.
   - Never push unverified code or broken syntax/unused imports to remote branches.

6. **Git Commit Standards**:
   - Always write structured Conventional Commits (`type(scope): summary`).
   - Always provide a detailed commit body describing *why* the change was made and a bulleted breakdown of modified components. Never use vague one-liners.


