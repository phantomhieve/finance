# Financial Precision, Multi-Tenancy & Security Rules

1. **Secrets Policy**:
   - Follow [`.agents/rules/no-secrets.md`](no-secrets.md) strictly: never read, grep, echo, or commit secret files or environment dumps.

2. **Financial Precision & Indian Fiscal Conventions**:
   - Use Python `Decimal` exclusively for currency amounts, interest rates, weights, and holdings; never use `float` for monetary balances or aggregations.
   - Quantize currency and percentage results to `Decimal('0.01')` or whole rupees (`Decimal('0')`), using `pct(part, total)` and `pnl_pct(pnl, invested)` from `pftracker.utils`.
   - Use the Indian Financial Year (April 1 – March 31; Jan–Mar belong to prior calendar year's FY) via `fy_start_year(date)` and `fy_label(fy_start)` in `pftracker.utils`.
   - Format rupee values in templates using `{% load indian_format %}` (`|inr`, `|inr_short`, `|indian_number` from `portfolio/templatetags/indian_format.py`).

3. **Multi-Tenancy & Access Control**:
   - Scope every group-owned queryset to the authenticated user's `AccountGroup` using fail-closed filtering (`_gf(group)` returns `{"id__in": []}` when `group is None`).
   - Enforce `_vault_gate` (`30-minute` password or WebAuthn passkey session TTL + brute-force lockout) on all `portfolio` and `jewellery` endpoints, and `EXPENSES_UNLOCK_TTL` on `expenses` when a vault password is set.
   - Enforce `_hides_investments(request)` (`hide_investments=True`) across all `expenses` views, totals (`month_summary`, `fy_summary`), and categorization rules so non-primary members (`ACCOUNT_HOLDER`) never access `INVESTMENT_CATEGORY` records.
   - Require `@require_POST` + CSRF verification on every state-changing endpoint, and validate `next` redirect targets via `url_has_allowed_host_and_scheme`.
