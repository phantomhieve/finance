#!/usr/bin/env bash
# Deploy application code and install cron. See scripts/DEPLOY.env.example.
#
# Does NOT upload or overwrite: .env, credentials/, portfolio/investor_profile.md, db.sqlite3
# Does NOT touch nginx, systemd unit files, or database backups.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${DEPLOY_HOST:?set DEPLOY_HOST}"
USER="${DEPLOY_USER:?set DEPLOY_USER}"
SSH_PORT="${DEPLOY_SSH_PORT:-22}"
REMOTE_APP="${DEPLOY_APP_DIR:?set DEPLOY_APP_DIR}"
APP_OWNER="${DEPLOY_APP_OWNER:?set DEPLOY_APP_OWNER}"
SERVICE_NAME="${DEPLOY_SERVICE_NAME:-vault}"
CRON_NAME="${DEPLOY_CRON_NAME:-vault}"
CRON_LOG="${DEPLOY_CRON_LOG:-/var/log/vault/cron.log}"
STATIC_DIR="${DEPLOY_STATIC_DIR:-}"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -p "$SSH_PORT")
if [[ -n "${SSH_KEY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY_FILE")
fi
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

if [[ "$USER" == "$APP_OWNER" ]]; then
  RSYNC_FLAGS=(-avz)
else
  RSYNC_FLAGS=(-rlvz --no-times --omit-dir-times)
fi

RSYNC_EXCLUDES=(
  --exclude '.git/'
  --exclude '.github/'
  --exclude '.cursor/'
  --exclude 'venv/'
  --exclude '.venv/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude 'db.sqlite3'
  --exclude '.env'
  --exclude '.env.*'
  --exclude 'credentials/'
  --exclude 'portfolio/investor_profile.md'
  --exclude 'staticfiles/'
  --exclude 'seed_data.py'
  --exclude 'seed_*.py'
)

echo "==> Deploy ${USER}@${HOST}:${REMOTE_APP}"

rsync "${RSYNC_FLAGS[@]}" \
  "${RSYNC_EXCLUDES[@]}" \
  -e "$RSYNC_SSH" \
  "${ROOT}/" "${USER}@${HOST}:${REMOTE_APP}/"

ACTIVATE_SCRIPT=/usr/local/sbin/vault-deploy-activate.sh

if [[ "$USER" == "$APP_OWNER" ]]; then
  echo "==> Activate inline (deploy user is app owner)"
  ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" \
    APP_DIR="${REMOTE_APP}" \
    APP_OWNER="${APP_OWNER}" \
    SERVICE_NAME="${SERVICE_NAME}" \
    CRON_NAME="${CRON_NAME}" \
    CRON_LOG="${CRON_LOG}" \
    STATIC_DIR="${STATIC_DIR}" \
    bash -es <<'EOS'
set -euo pipefail
cd "${APP_DIR}"
mkdir -p venv
[[ -x venv/bin/python ]] || python3 -m venv venv
set -a && [[ -f .env ]] && . ./.env; set +a
venv/bin/pip install -q -r requirements.txt
venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py collectstatic --noinput
if [[ -n "${STATIC_DIR}" ]]; then
  sudo mkdir -p "${STATIC_DIR}"
  sudo rsync -a --delete staticfiles/ "${STATIC_DIR}/"
fi
sudo mkdir -p "$(dirname "${CRON_LOG}")" && sudo touch "${CRON_LOG}"
sed -e "s|__APP_DIR__|${APP_DIR}|g" -e "s|__APP_OWNER__|${APP_OWNER}|g" \
    -e "s|__CRON_LOG__|${CRON_LOG}|g" -e "s|__CRON_NAME__|${CRON_NAME}|g" \
    deploy/cron | sudo tee "/etc/cron.d/${CRON_NAME}" >/dev/null
sudo chmod 644 "/etc/cron.d/${CRON_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl is-active --quiet "${SERVICE_NAME}"
EOS
else
  echo "==> Activate via sudo ${ACTIVATE_SCRIPT}"
  ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "sudo ${ACTIVATE_SCRIPT}"
fi

if [[ -n "${DEPLOY_HEALTHCHECK_URL:-}" ]] && command -v curl >/dev/null; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -L "${DEPLOY_HEALTHCHECK_URL}" || echo "000")
  echo "==> Health check HTTP ${code}"
fi

echo "==> Deploy complete"
