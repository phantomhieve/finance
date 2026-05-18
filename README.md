# Vault — Personal Finance Dashboard

A Django-based personal finance tracker covering monthly savings goals, HRA/rent management, and a full investment portfolio tracker with automated data sync, commodity price refresh, and nightly database backups.

## Features

- **Monthly Savings Tracker** — Set annual/monthly goals, track savings, transfers, and extra income per FY (April-March)
- **HRA & Rent Tracker** — Track rent paid, expenses, and reverts with balance tracking
- **Portfolio Tracker** — EPF, NPS, Zerodha (Stocks, Index Funds, MFs), FDs, Cash, Bonds, Crypto, Gold & Silver
- **Consolidated Zerodha Dashboard** — Allocation chart, P&L summary, top gainers/losers, sortable tables
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
| Account Holder | Full CRUD | Grayed out | Full CRUD | No |
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

## Scheduled Tasks (Cron)

See `deploy-your-ssh-host-or-ip/vault-cron` (uses `CRON_TZ=Asia/Kolkata`).

| Schedule | Command |
|----------|---------|
| Daily 6 AM IST | `sync_sheets` then `refresh_prices` — Sheets + commodity rates |
| 1st of month 6 AM IST | `take_snapshot` — Monthly portfolio snapshot |
| Daily 11:30 PM IST | `backup_db` — Database backup to GCS |

## Production Deployment

Deployed on Ubuntu 24.04 via Cloudflare Tunnel.

```
Browser → Cloudflare Tunnel (HTTPS) → Nginx (:80) → Gunicorn (:8000) → Django → PostgreSQL
```

See `deploy-your-ssh-host-or-ip/` for Nginx, systemd, and cron (YouStable).

```bash
cd /path/to/app && source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart vault
sudo cp deploy-your-ssh-host-or-ip/vault-cron /etc/cron.d/vault && sudo chmod 644 /etc/cron.d/vault && sudo chown root:root /etc/cron.d/vault
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
| `GEMINI_API_KEY` | AI portfolio insights |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` | Biometric unlock (must match browser URL) |
| `VAULT_HEALTH_CHECK_URL` / `VAULT_HEALTH_CHECK_HOST` | Optional admin monitor probe |
| `GUNICORN_*` | Bind address, workers, log paths (see `.env.example`) |

## Credentials

Set `GOOGLE_SHEETS_CREDENTIALS` to the path of your service account JSON (e.g. `credentials/google-service-account.json`). Used for Google Sheets sync and GCS uploads. The `credentials/` directory is gitignored.

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
├── templates/          # Shared templates
├── static/             # CSS, JS assets
├── credentials/        # Google service account (gitignored; paths via .env)
└── scripts/            # Operational scripts (configure via .env)
```
