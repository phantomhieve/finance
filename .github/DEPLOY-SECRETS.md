# GitHub Actions Deploy Secrets

Configure under **Settings → Secrets and variables → Actions**.
Application runtime secrets (Django, database, OAuth, AI keys) live strictly in `.env` on the server.

## Required

| Secret | Description |
|--------|-------------|
| `DEPLOY_SSH_PRIVATE_KEY` | Deploy SSH private key (full PEM) |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user for deployment |
| `DEPLOY_APP_DIR` | Application root directory on server |
| `DEPLOY_APP_OWNER` | UNIX user that owns the app and runs cron |

## Optional

| Secret | Default |
|--------|---------|
| `DEPLOY_SSH_PORT` | `22` |
| `DEPLOY_KNOWN_HOSTS` | *(first-use `ssh-keyscan` fallback; set `ssh-keyscan -H <host>` to pin host key)* |
| `DEPLOY_STATIC_DIR` | *(skip static rsync)* |
| `DEPLOY_SERVICE_NAME` | `vault` |
| `DEPLOY_CRON_NAME` | `vault` |
| `DEPLOY_CRON_LOG` | `/var/log/vault/cron.log` |
| `DEPLOY_HEALTHCHECK_URL` | *(skip)* |

## CI/CD Pipeline (`.github/workflows/ci.yml`)

| Job | Trigger | Steps |
|-----|---------|-------|
| `check` | Every push / PR / manual dispatch | `ruff check --select F,E9 .`, `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, `manage.py test --noinput`, `pip-audit -r requirements.txt` |
| `deploy` | After `check` succeeds on push to `main`/`master` or `workflow_dispatch` | SSH configuration + `./scripts/deploy.sh` |

For manual local deploys, copy `scripts/DEPLOY.env.example` to `scripts/DEPLOY.env` (gitignored).
