#!/usr/bin/env bash
# One-time: least-privilege deploy user (same model as cashcenter).
# Run as root on the app server:
#   sudo APP_OWNER=atul APP_DIR=/path/to/app \
#        DEPLOY_USER=vault-deploy DEPLOY_PUBKEY="$(cat deploy.pub)" \
#        bash setup-deploy-user.sh
#
# Optional: STATIC_DIR, SERVICE_NAME, CRON_NAME, CRON_LOG (defaults below).

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-vault-deploy}"
APP_OWNER="${APP_OWNER:?set APP_OWNER}"
APP_DIR="${APP_DIR:?set APP_DIR}"
ACTIVATE_SCRIPT=/usr/local/sbin/vault-deploy-activate.sh
GROUP="${DEPLOY_GROUP:-vault}"
STATIC_DIR="${STATIC_DIR:-/var/www/vault/static}"
SERVICE_NAME="${SERVICE_NAME:-vault}"
CRON_NAME="${CRON_NAME:-vault}"
CRON_LOG="${CRON_LOG:-/var/log/vault/cron.log}"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/manage.py" ]]; then
  echo "Missing ${APP_DIR}/manage.py — set APP_DIR." >&2
  exit 1
fi

echo "==> Group and user: ${DEPLOY_USER}"
groupadd -f "$GROUP"
if ! id "$DEPLOY_USER" &>/dev/null; then
  useradd -m -s /bin/bash -g "$GROUP" "$DEPLOY_USER"
fi
chmod 700 "/home/${DEPLOY_USER}"

# Deploy user must traverse app owner's home for rsync path
if [[ -d "/home/${APP_OWNER}" ]]; then
  chmod 751 "/home/${APP_OWNER}"
fi
usermod -aG "$GROUP" "$APP_OWNER" 2>/dev/null || true

echo "==> Permissions: ${DEPLOY_USER} group-write on app tree (not .env or credentials)"
chgrp -R "$GROUP" "$APP_DIR"
chmod -R g+rwX "$APP_DIR"
find "$APP_DIR" -type d -exec chmod g+s {} +
if [[ -f "${APP_DIR}/.env" ]]; then
  chown "${APP_OWNER}:${APP_OWNER}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi
if [[ -d "${APP_DIR}/credentials" ]]; then
  chown -R "${APP_OWNER}:${APP_OWNER}" "${APP_DIR}/credentials"
  chmod -R u=rwX,go= "${APP_DIR}/credentials"
fi
if [[ -f "${APP_DIR}/portfolio/investor_profile.md" ]]; then
  chown "${APP_OWNER}:${APP_OWNER}" "${APP_DIR}/portfolio/investor_profile.md"
  chmod 600 "${APP_DIR}/portfolio/investor_profile.md"
fi
chmod g+s "$APP_DIR" 2>/dev/null || true

echo "==> Activate script: ${ACTIVATE_SCRIPT}"
install -m 0755 /dev/stdin "$ACTIVATE_SCRIPT" <<EOS
#!/usr/bin/env bash
set -euo pipefail
APP="${APP_DIR}"
APP_OWNER="${APP_OWNER}"
STATIC_DIR="${STATIC_DIR}"
SERVICE_NAME="${SERVICE_NAME}"
CRON_NAME="${CRON_NAME}"
CRON_LOG="${CRON_LOG}"

cd "\$APP"
mkdir -p venv
if [[ ! -x venv/bin/python ]]; then
  sudo -u "\$APP_OWNER" python3 -m venv venv
fi

sudo -u "\$APP_OWNER" "\$APP/venv/bin/pip" install -q -r requirements.txt
sudo -u "\$APP_OWNER" bash -c 'cd "'"\$APP"'" && set -a && [ -f .env ] && . ./.env; set +a && venv/bin/python manage.py migrate --noinput'
sudo -u "\$APP_OWNER" bash -c 'cd "'"\$APP"'" && set -a && [ -f .env ] && . ./.env; set +a && venv/bin/python manage.py collectstatic --noinput'

if [[ -n "\$STATIC_DIR" ]]; then
  mkdir -p "\$STATIC_DIR"
  rsync -a --delete "\$APP/staticfiles/" "\$STATIC_DIR/"
fi

mkdir -p "\$(dirname "\$CRON_LOG")"
touch "\$CRON_LOG"
chown "\$APP_OWNER:\$APP_OWNER" "\$CRON_LOG" 2>/dev/null || true

sed -e "s|__APP_DIR__|\$APP|g" -e "s|__APP_OWNER__|\$APP_OWNER|g" -e "s|__CRON_LOG__|\$CRON_LOG|g" -e "s|__CRON_NAME__|\$CRON_NAME|g" "\$APP/deploy/cron" > "/etc/cron.d/\${CRON_NAME}"
chmod 644 "/etc/cron.d/\${CRON_NAME}"
chown root:root "/etc/cron.d/\${CRON_NAME}"

systemctl restart "\${SERVICE_NAME}"
sleep 2
systemctl is-active --quiet "\${SERVICE_NAME}"
echo "\${SERVICE_NAME}.service: active"
EOS

echo "==> sudoers"
install -m 0440 /dev/stdin /etc/sudoers.d/vault-deploy <<EOF
# Managed by finance setup-deploy-user.sh — ${DEPLOY_USER} may only run activate.
Defaults:${DEPLOY_USER} !requiretty
${DEPLOY_USER} ALL=(root) NOPASSWD: ${ACTIVATE_SCRIPT}
EOF
visudo -cf /etc/sudoers.d/vault-deploy

echo "==> SSH authorized_keys for ${DEPLOY_USER}"
install -d -m 700 -o "$DEPLOY_USER" -g "$GROUP" "/home/${DEPLOY_USER}/.ssh"
touch "/home/${DEPLOY_USER}/.ssh/authorized_keys"
chown "$DEPLOY_USER:$GROUP" "/home/${DEPLOY_USER}/.ssh/authorized_keys"
chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys"

if [[ -n "${DEPLOY_PUBKEY:-}" ]]; then
  if ! grep -qF "$DEPLOY_PUBKEY" "/home/${DEPLOY_USER}/.ssh/authorized_keys"; then
    echo "$DEPLOY_PUBKEY" >>"/home/${DEPLOY_USER}/.ssh/authorized_keys"
  fi
  echo "Public key installed."
else
  echo "Set DEPLOY_PUBKEY and re-run to install deploy public key."
fi

echo "==> Done."
echo "    Add ${DEPLOY_USER} to sshd AllowUsers if restricted."
