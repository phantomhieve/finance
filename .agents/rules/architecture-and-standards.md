# Architecture, Contracts & Code Standards

Guidelines for Antigravity agents modifying or extending the Vault Personal Finance codebase.

---

## 1. Python, Typing & Django Conventions

- **Target Runtime**: Python 3.14 + Django 6.0 compatibility.
- **Strict Typing**:
  - All new or refactored functions, service methods, and helpers MUST include complete type hints.
  - Use Python 3.10+ union syntax (`T | None` instead of `Optional[T]`, `list[str]` instead of `List[str]`).
  - Money amounts MUST be typed as `Decimal`, never `float`.
- **Docstring Standards**:
  - Every module, class, public service function, and complex utility MUST have a clear docstring.
  - Describe parameters, return types, exceptions raised, and multi-tenancy scoping.
- **Clean Separation of Concerns**:
  - **Models** in `<app>/models.py`: define schema, field validations, clean representation (`__str__`), and model-level properties.
  - **Business Logic & External APIs** in `<app>/services.py`: aggregations, synchronization, third-party integrations, and complex math.
  - **Forms** in `<app>/forms.py`: data validation, sanitization, and UI form specifications.
  - **Views** in `<app>/views.py`: request parsing, security/role gating, context assembly, and response formatting. Keep views thin.
  - **Background Commands** in `<app>/management/commands/`.

---

## 2. App Boundaries & Module Contracts

| App | Contract / Scope | Invariants |
| :--- | :--- | :--- |
| **`tracker`** | Custom auth (`User`, `AccountGroup`), FY savings vs goal pacing, HRA tracking, personal notes. | User-scoped via `group_user_filter(user)`. Role permissions (`PRIMARY`, `ACCOUNT_HOLDER`, `LANDLORD`) strictly checked. Feature gates (`notes`, `hra`) enforced. |
| **`portfolio`** | Multi-asset wealth management, Zerodha sync, live price services, multi-stage AI insights DAG. | Gated behind `_vault_gate` with session unlock TTL. Group-scoped via `_user_group(request)`. Master vs Child portfolio separation via `is_baby`. |
| **`expenses`** | Bank statement parsing, transaction reconciliation, Gmail sync, EMI tracking, AI anomaly detection. | Group-scoped. Investment category (`INVESTMENT_CATEGORY`) masked from non-primary holders via `_hides_investments`. Reconciled dual-leg transfers collapsed. |
| **`jewellery`** | Physical precious metal inventory, locker vs safe location tracking, live fineness valuation. | Gated behind `_vault_gate`. Live rates attached via `JewelleryItem.attach_rates` to prevent per-item N+1 queries. WebP thumbnail caching. |
| **`pftracker`** | Core settings, ASGI dual router (`/mcp` + Django HTTP), AI gateway router, connection pooling & concurrency. | Concurrency must use `DjangoSafeThreadPoolExecutor` or `safe_async_to_thread` to prevent database connection leaks. |
| **`mcp_server`** | FastMCP SSE tools & resources for external AI clients. | Requires OAuth 2.0 PKCE tokens. Write mutations require `write` scope and PRIMARY user. Every mutation MUST write an immutable before/after snapshot to `MCPAuditLog`. |

---

## 3. Anti-N+1 Query & Database Performance Rules

1. **Mandatory Query Optimization**:
   - Always apply `.select_related()` for single-valued relationships (`ForeignKey`, `OneToOneField`) accessed in templates, loops, or serializers.
   - Always apply `.prefetch_related()` for multi-valued relationships (`ManyToManyField`, reverse `ForeignKey`).
   - When fetching records by ID list, use `.in_bulk()` or `__in` queries instead of querying one-by-one.
2. **Bulk Operations**:
   - Use `bulk_create` and `bulk_update` with `batch_size` for multi-row inserts/updates.
   - Specify `update_fields` when saving existing model instances to avoid full-row overwrites and race conditions.
3. **Database Concurrency & Locking Prevention**:
   - SQLite operates in WAL mode with a 15-second busy timeout (`pftracker/db_optimizations.py`).
   - Long-running async or background operations MUST NOT hold transactions open.
4. **Caching Invariants**:
   - Cache expensive aggregations or lockout trackers using Django's cache framework (`from django.core.cache import cache`).
   - Prefix cache keys with tenant identifiers (e.g. `vault_unlock_{group_id}`).

---

## 4. Error Recovery & Fault Tolerance

1. **Multi-Stage DAG Resilience**:
   - AI analytical pipelines (such as `PortfolioInsightsDAG` and `run_land_appraisal_dag`) MUST implement deterministic fallbacks for EVERY stage (Stages 1A/B/C, 2, and 3).
   - Under network outages, rate limits, or model provider timeouts, the pipeline must degrade gracefully and return grounded deterministic assessments rather than crashing.
2. **Graceful Degradation on Third-Party APIs**:
   - Google Sheets sync, Gmail sync, commodity rate scrapers, and currency exchange APIs must catch connection/timeout errors, log structured warnings, and use cached rates/data.
3. **Exception Specificity**:
   - Never use bare `except:`. Always catch specific exception types (`(ValueError, KeyError, ObjectDoesNotExist, RequestException)`).
   - Log exceptions with contextual metadata (tenant group ID, entity PK).
