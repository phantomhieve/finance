# Vault — Personal Finance Dashboard

A Django-based personal finance tracker covering monthly savings goals, HRA/rent management, and a full investment portfolio tracker with automated data sync, commodity price refresh, and nightly database backups.

## Features

- **Monthly Savings Tracker** — Set annual/monthly goals, track savings, transfers, and extra income per FY (April-March)
- **HRA & Rent Tracker** — Track rent paid, expenses, and reverts with balance tracking
- **Portfolio Tracker** — EPF, NPS, Zerodha (Stocks, Index Funds, MFs), FDs, Cash, Bonds, Crypto, Gold & Silver
- **Consolidated Zerodha Dashboard** — Allocation chart, P&L summary, top gainers/losers, sortable tables
- **Expense Tracker** — Household spend auto-detected from bank / card alert emails in one or more connected Gmail inboxes; AI + learned categorisation, card statement reconciliation, bill reminders, suspicious-transaction flags and a monthly household email (see [Expense Tracker](#expense-tracker))
- **Financial Goals** — Track progress toward financial goals grouped by FY
- **Commodity Prices** — Live gold (24K) and silver prices from goodreturns.in (no API key needed)
- **Google Sheets Sync** — Auto-sync Zerodha holdings from Google Sheets
- **Automated Backups** — Nightly PostgreSQL dump → gzip → Google Cloud Storage
- **Role-Based Access** — Three user types with group-based data sharing
- **Dark-Themed UI** — Glass-morphism design with Chart.js visualizations

## User Roles

| Role | Dashboard | Portfolio | HRA | Admin |
|------|-----------|-----------|-----|-------|
| Primary Account Holder | Full CRUD | Full access | Full CRUD | Yes |
| Account Holder | Full CRUD | No access | Full CRUD | No |
| Landlord | No access | No access | View only | No |

Users in the same **AccountGroup** share all financial data.

## Tech Stack

- Python 3.14, Django 6.0
- PostgreSQL (production) / SQLite (development)
- Gunicorn + Nginx (production)
- Cloudflare Tunnel (HTTPS)
- Chart.js 4.4, django-crispy-forms + Bootstrap 5
- Google Cloud Storage (backups), gspread (Sheets sync)

## Local Development

```bash
python3.14 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python seed_data.py

python manage.py runserver
```

### Seed Users

| Username | Password | Role |
|----------|----------|------|
| atul | password123 | Primary Account Holder |
| spouse | password123 | Account Holder |
| landlord | password123 | Landlord |

## Management Commands

| Command | Description |
|---------|-------------|
| `refresh_prices` | Fetch latest gold/silver prices from goodreturns.in |
| `sync_sheets` | Sync Zerodha holdings from Google Sheets |
| `take_snapshot` | Capture monthly portfolio snapshot |
| `backup_db --bucket NAME` | Dump PostgreSQL, gzip, upload to GCS |
| `sync_expenses [--email X]` | Pull new bank / card alert emails from connected Gmail inboxes |
| `expense_reminders` | Email card bill reminders (5 days, 1 day, due day, overdue) |
| `send_expense_summary [--month YYYY-MM] [--preview PATH]` | Monthly household spend email (mail-detected only) |

## Scheduled Tasks (Cron)

Example schedule (set `CRON_TZ=Asia/Kolkata` if needed):

| Schedule | Command |
|----------|---------|
| Daily 6 AM IST | `sync_sheets` then `refresh_prices` — Sheets + commodity rates |
| 1st of month 6 AM IST | `take_snapshot` — Monthly portfolio snapshot |
| Daily 11:30 PM IST | `backup_db` — Database backup to GCS |
| Hourly at :17 | `sync_expenses` — Gmail bank / card alerts |
| Daily 9 AM IST | `expense_reminders` — Card bill reminders |
| 1st of month 8 AM IST | `sync_expenses` then `send_expense_summary` — Last month's household spend |

## Expense Tracker

`/expenses/` — visible to Primary and Account Holder users (toggle: *Household config → Expense tracker*).

**How it works**

1. Each household member connects their own Gmail from *Expenses → Settings* — as many inboxes as needed: tap *Add another inbox* once per address and pick it in Google's account chooser. Every inbox syncs independently and all spends land in the one household view. Vault requests the read-only `gmail.readonly` scope, stores the refresh token encrypted, and never stores email bodies — only the parsed transaction and a masked subject.
2. The hourly sync searches for transaction-style emails (content-based, so it survives banks moving sender domains), parses amount / merchant / card / date with bank-specific patterns, and falls back to Gemini for formats it doesn't recognise.
3. Categories are assigned in order: **your rules** → cached AI rules → built-in brands & keywords → Gemini. Changing a category teaches Vault that merchant and re-files its past transactions. Investments, transfers and card bill payments are tracked but never counted as spend.
4. Credit card statement emails are detected automatically. The PDF (password saved per card, encrypted) is matched line by line against alerts; anything the bank never alerted on is added. Due dates trigger reminders, and a "payment received" email marks the bill paid.
5. Rule-based flags catch unusual amounts for a category, large first-time merchants, possible double charges, foreign currency, odd hours and rapid-fire card use. Flagged items lead the monthly email.

**Google Cloud setup** (same project as the login OAuth client)

1. Enable the **Gmail API**.
2. OAuth consent screen: add the `.../auth/gmail.readonly` scope and set publishing status to **In production**. In *Testing* mode refresh tokens expire after 7 days and only listed test users can connect. An unverified app is fine for a household (up to 100 Google accounts) — each inbox sees a one-time "unverified app" warning.
3. Add `<VAULT_PUBLIC_URL>/expenses/gmail/callback/` to the OAuth client's authorised redirect URIs.
4. Optionally set `EXPENSES_ENCRYPTION_KEY` (otherwise derived from `DJANGO_SECRET_KEY` — rotating that key would then require reconnecting inboxes and re-entering statement passwords).

## Production Deployment

Typical stack: HTTPS reverse proxy or tunnel → Gunicorn → Django → PostgreSQL.

```bash
cp .env.example .env   # set production values
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn pftracker.wsgi:application -c gunicorn.conf.py
```

## Environment Variables

Copy `.env.example` to `.env` and fill in values. Never commit `.env` or files under `credentials/`.

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Django secret key (required in production) |
| `DJANGO_DEBUG` | `True` / `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins (include `https://` in prod) |
| `DATABASE_URL` | PostgreSQL URL; omit for SQLite dev |
| `VAULT_PUBLIC_URL` | Public site URL (e.g. `https://finance.example.com`) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google login (allauth) |
| `GOOGLE_SHEETS_CREDENTIALS` | Path to service account JSON (Sheets + GCS backup) |
| `BACKUP_GCS_BUCKET` | GCS bucket for `backup_db` |
| `BACKUP_SA_JSON_PATH` | Service account JSON for `scripts/backup-all-dbs.sh` |
| `BACKUP_DATABASES` | Space-separated DB names for multi-DB backup script |
| `GEMINI_API_KEY` | AI portfolio insights and expense categorisation |
| `EXPENSES_ENCRYPTION_KEY` | Fernet key for Gmail tokens + statement passwords (optional) |
| `EXPENSES_GEMINI_MODEL` | Override the model used for expense categorisation (optional) |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` | Biometric unlock (must match browser URL) |
| `VAULT_HEALTH_CHECK_URL` / `VAULT_HEALTH_CHECK_HOST` | Optional admin monitor probe |
| `GUNICORN_*` | Bind address, workers, log paths (see `.env.example`) |

## Credentials

Set `GOOGLE_SHEETS_CREDENTIALS` to the path of your service account JSON (e.g. `credentials/google-service-account.json`). Used for Google Sheets sync and GCS uploads. The `credentials/` directory is gitignored.

For AI insights, copy `portfolio/investor_profile.md.example` → `portfolio/investor_profile.md` (gitignored) with your household details — never commit real names or employer info.

## Project Structure

```
personal-finance/
├── pftracker/          # Django project config
├── tracker/            # Monthly savings + HRA app
├── portfolio/          # Portfolio tracker app
│   ├── management/commands/  # refresh_prices, sync_sheets, take_snapshot, backup_db
│   ├── models.py       # All portfolio models
│   ├── services.py     # Business logic, API integrations
│   └── views.py        # Portfolio views
├── expenses/           # Expense tracker: Gmail sync, parsing, categorisation, statements, anomalies
├── templates/          # Shared templates
├── static/             # CSS, JS assets
├── credentials/        # Google service account (gitignored; paths via .env)
└── scripts/            # Operational scripts (configure via .env)
```
