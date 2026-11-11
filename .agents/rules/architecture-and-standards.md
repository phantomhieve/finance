# Architecture, Contracts & Code Standards

Guidelines for agents modifying or extending the Vault codebase.

---

## 1. Python, Typing & Django Conventions

- **Target Runtime**: Python 3.12+ and Django 6.0.
- **Strict Typing**:
  - Include complete type hints (`T | None`, `list[str]`, `Decimal`) on all new or refactored functions, methods, and classes.
  - Type monetary figures, weights, and rates exclusively as `Decimal`, never `float`.
- **Docstring Standards**:
  - Document parameters, return types, exceptions raised, and `AccountGroup` tenant scoping on public service functions and classes.
- **Separation of Concerns**:
  - **Models** (`<app>/models.py`): Schema, field validators, `__str__`, and pure model properties.
  - **Services & Domain Modules** (`<app>/services.py`, `dag.py`, `land_appraisal.py`, `analytics.py`, `ingestion.py`, `statements.py`): Business logic, external APIs, synchronization, and `Decimal` calculations.
  - **Forms** (`<app>/forms.py`): Validation and sanitization.
  - **Views** (`<app>/views.py`): Request parsing, role/vault gating, context assembly, and response rendering.
  - **Management Commands** (`<app>/management/commands/`): Scheduled and operational CLI entrypoints.

---

## 2. App Boundaries & Module Contracts

| App | Responsibility | Key Invariants |
| :--- | :--- | :--- |
| **`pftracker`** | Settings, dual ASGI router (`/mcp` + Django HTTP), Unified AI Gateway (`ai_gateway/`), DB pooling & safe concurrency (`concurrency.py`, `db_optimizations.py`). | Thread/async workers must use `DjangoSafeThreadPoolExecutor` or `safe_async_to_thread` to prevent DB connection leaks. |
| **`tracker`** | Custom auth (`User`, `AccountGroup`, `HouseholdConfig`), FY savings vs. goal pacing, HRA ledger, personal notes, WebAuthn credentials. | User-scoped via resolved household owner or `group_user_filter(user)`. Role gates (`PRIMARY`, `ACCOUNT_HOLDER`, `LANDLORD`) and feature flags enforced. |
| **`portfolio`** | 11-asset-class wealth engine, Google Sheets sync, live bullion/FX rates, `indian_format` filters, Portfolio & Land AI DAGs. | Gated behind `_vault_gate` (`30m` TTL). Group-scoped via `_gf(group)` fail-closed filter. Master vs. Child split via `is_baby`. |
| **`expenses`** | Gmail OAuth sync, statement PDF unlocking & 3-stage reconciliation, dual-leg transfer settlement, EMI tracking, 4-tier categorization, AI audit. | Group-scoped. `INVESTMENT_CATEGORY` masked from non-primary members via `_hides_investments`. Optional `EXPENSES_UNLOCK_TTL` session lock. |
| **`jewellery`** | Precious metal & ornament custody ledger (`BANK_LOCKER` vs. `HOME_SAFE`), fineness valuation, UUID photo storage, WebP thumbnails. | Gated behind `_vault_gate`. Live rates attached via `JewelleryItem.attach_rates` (zero per-item N+1 queries). |
| **`mcp_server`** | FastMCP SSE tools & resources for external AI clients. | OAuth 2.0 PKCE (`RFC 9700`) required; `PRIMARY` role enforced; write tools require `write` scope and log reversible snapshots in `MCPAuditLog`. |

---

## 3. Anti-N+1 Query & Database Performance Rules

1. **Relationship Prefetching**:
   - Use `.select_related()` for `ForeignKey` / `OneToOneField` relations and `.prefetch_related()` for `ManyToManyField` / reverse `ForeignKey` relations accessed in loops, templates, or serializers.
   - Use `.in_bulk()` or `__in` filters rather than per-ID queries inside loops.
2. **Bulk & Scoped Writes**:
   - Use `bulk_create` and `bulk_update` with `batch_size` for multi-row mutations.
   - Pass `update_fields=[...]` when saving existing model instances to avoid clobbering concurrent column updates.
3. **Concurrency & Cache Keys**:
   - Never hold database transactions open across external HTTP or LLM network calls.
   - Prefix cache keys (`django.core.cache`) with tenant identifiers (`group.id`) to guarantee multi-tenant isolation.

---

## 4. Error Recovery & Fault Tolerance

1. **Quant-Grounded AI DAG Resilience**:
   - Pre-compute deterministic `Decimal` metrics in Python before invoking LLM nodes, and provide data-grounded Python fallbacks for every stage (`PortfolioInsightsDAG`, `run_land_appraisal_dag`).
   - Provider rate limits (`HTTP 429`), errors (`HTTP 5xx`), or timeouts must degrade gracefully without failing requests or cron runs.
2. **Third-Party API Safety**:
   - Catch specific exceptions (`ObjectDoesNotExist`, `ValueError`, `KeyError`, `RequestException`) on Google Sheets, Gmail, FX, and bullion scrapers; never use bare `except:`.
