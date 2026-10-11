# CodeGraph Navigation & Intelligence Rules

When exploring, navigating, refactoring, or analyzing the Vault codebase:

1. **Use CodeGraph First**:
   - Prefer querying CodeGraph via its MCP tools (`codegraph_query`, `codegraph_node`, `codegraph_explore`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`, `codegraph_affected`) or CLI commands (`codegraph query`, `codegraph node`, etc.) over blind ripgrep searches.
   - CodeGraph maintains an AST-level symbol graph in `.codegraph/` that avoids token bloat and maps precise caller/callee relationships.

2. **Refactoring & Blast Radius Analysis**:
   - Before modifying functions, model fields, or service signatures in core files (`pftracker/utils.py`, `portfolio/services.py`, `tracker/services.py`, `expenses/services.py`), run `codegraph impact <symbol>` or use `codegraph_impact` to identify all downstream consumers.
   - Run `codegraph affected` on changed files to identify affected tests.

3. **Index Hygiene**:
   - The `.codegraph/` database directory is strictly ignored in version control (`.gitignore`).
   - If new files or significant structural refactoring occurs, run `codegraph sync` in the terminal to keep the knowledge graph synchronized with disk changes.
