# GitHub Actions secrets

**Settings → Secrets and variables → Actions**

App secrets (Django, DB, OAuth, API keys) stay on the server in `.env` only.

## Required

| Secret | Description |
|--------|-------------|
| `DEPLOY_SSH_PRIVATE_KEY` | Deploy SSH private key (full PEM) |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user (e.g. dedicated deploy user) |
| `DEPLOY_APP_DIR` | Application root on server |
| `DEPLOY_APP_OWNER` | UNIX user that owns the app and runs cron |

## Optional

| Secret | Default |
|--------|---------|
| `DEPLOY_SSH_PORT` | `22` |
| `DEPLOY_STATIC_DIR` | *(skip static rsync)* |
| `DEPLOY_SERVICE_NAME` | `vault` |
| `DEPLOY_CRON_NAME` | `vault` |
| `DEPLOY_CRON_LOG` | `/var/log/vault/cron.log` |
| `DEPLOY_HEALTHCHECK_URL` | *(skip)* |

## Workflows

| File | Trigger |
|------|---------|
| `.github/workflows/ci.yml` | push/PR → `manage.py check` |
| `.github/workflows/deploy.yml` | push to `main` / manual → check + `./scripts/deploy.sh` |

Local deploy: copy `scripts/DEPLOY.env.example` → `scripts/DEPLOY.env` (gitignored).
