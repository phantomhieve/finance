# Financial Precision, Security & Data Handling Rules

1. **Absolute Ban on Exposing Secrets**:
   - NEVER read, dump, print, or commit `.env`, `scripts/DEPLOY.env`, `.deploy-keys/`, `credentials/`, `*.pem`, `*.key`, `portfolio/investor_profile.md`, or service account JSON files.
   - NEVER query the database or Django shell to print user password hashes, encrypted tokens, or WebAuthn credentials in chat or terminal logs.
   - Reference environment variable names only (e.g. `GOOGLE_SHEETS_CREDENTIALS`, `DJANGO_SECRET_KEY`) and refer users to `.env.example`.

2. **Financial Precision & Math**:
   - ALWAYS use Python's `Decimal` type for monetary amounts, interest rates, unit quantities, and holdings.
   - NEVER use `float` arithmetic for financial totals, balances, or transactions.
   - Quantize calculated values to 2 decimal places (`.quantize(Decimal('0.01'))`) or integer rupees (`.quantize(Decimal('0'))`) as appropriate.
   - Percentage returns must be formatted using the helper `pct(part, total)` or `pnl_pct(pnl, invested)` from `pftracker.utils`.

3. **Indian Fiscal Year Conventions**:
   - The fiscal cycle is April 1 through March 31.
   - Dates in January, February, or March belong to the previous calendar year's FY (e.g., February 2026 is FY 2025-26).
   - Use `fy_start_year(date)` and `fy_label(fy_start)` from `pftracker.utils` for consistent FY formatting.

4. **Multi-Tenancy & Access Isolation**:
   - Querysets MUST be scoped to the authenticated user's `group` (`AccountGroup`).
   - Sensitive investment portfolio and jewellery endpoints MUST remain protected behind `_vault_gate` with session expiration checks.
   - Household expenses tagged under `INVESTMENT_CATEGORY` MUST be excluded from views when accessed by non-primary account holders (`_hides_investments`).
