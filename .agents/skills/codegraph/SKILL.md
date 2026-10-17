---
name: codegraph
description: >-
  Use this skill to query, navigate, and analyze the codebase's structural knowledge graph,
  symbol definitions, call paths, callers/callees, and refactoring impact using CodeGraph.
---

# CodeGraph Code Intelligence & Knowledge Graph

CodeGraph maintains an AST-level, real-time knowledge graph of the repository in a local SQLite database (`.codegraph/`). It indexes files, classes, methods, functions, variables, routes, and imports.

Use CodeGraph instead of blind text searches (`grep`) whenever analyzing architecture, finding symbol definitions, tracing call hierarchies, or estimating the impact of a code modification.

---

## 1. When to Use CodeGraph

| Scenario | Recommended CodeGraph Workflow |
| :--- | :--- |
| **Locating a symbol or class** | `codegraph query <symbol>` (or `codegraph_query` MCP tool) |
| **Exploring a feature/area** | `codegraph explore "<feature query>"` (or `codegraph_explore` MCP tool) |
| **Inspecting symbol + call trail** | `codegraph node <symbol_name>` (or `codegraph_node` MCP tool) |
| **Finding callers of a function** | `codegraph callers <symbol_name>` (or `codegraph_callers` MCP tool) |
| **Finding functions called by a symbol** | `codegraph callees <symbol_name>` (or `codegraph_callees` MCP tool) |
| **Blast-radius & impact analysis** | `codegraph impact <symbol_name>` (or `codegraph_impact` MCP tool) |
| **Finding affected tests/files** | `codegraph affected [files...]` (or `codegraph_affected` MCP tool) |
| **Building task context** | `codegraph context "<task description>"` |

---

## 2. CLI Quick Reference

The CLI is installed globally at `/opt/homebrew/bin/codegraph`.

```bash
# Check index status and node/edge statistics
codegraph status

# Incremental synchronization after adding/editing files
codegraph sync

# Rebuild index from scratch if ever needed
codegraph index

# Query symbols (classes, functions, routes)
codegraph query get_portfolio_summary

# Explore a subsystem
codegraph explore "vault gate authorization"

# Trace callers and callees
codegraph callers _require_portfolio
codegraph callees portfolio_unlock

# Evaluate blast-radius before modifying a core function
codegraph impact fy_start_year
```

---

## 3. MCP Integration

CodeGraph runs as an MCP server via `/opt/homebrew/bin/codegraph serve --mcp`. When connected, the following tools are available to the agent:

1. `codegraph_query`: Fast lookup of symbol definitions, kinds, and declaring files.
2. `codegraph_node`: Full source snippet of a symbol along with its inbound (caller) and outbound (callee) connections.
3. `codegraph_explore`: Discovers relevant symbols, source snippets, and execution paths for a high-level topic.
4. `codegraph_context`: Packages contextual symbols and references for a specific development task.
5. `codegraph_callers`: Finds all upstream call sites invoking a specific symbol.
6. `codegraph_callees`: Finds all downstream dependencies invoked by a specific symbol.
7. `codegraph_impact`: Traces the dependency tree to identify everything that could be broken by modifying a symbol.
8. `codegraph_affected`: Identifies tests and consumers impacted by specific modified files.

---

## 4. Best Practices

- **Sync after edits**: When creating new files or restructuring existing modules, run `codegraph sync` to refresh graph edges.
- **Pre-refactor impact check**: Always run `codegraph impact <symbol>` before changing function signatures in core utilities (`pftracker/utils.py`, `portfolio/services.py`, `tracker/services.py`).
