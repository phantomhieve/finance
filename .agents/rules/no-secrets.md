# Strict Secrets & Credential Protection Policy

This rule applies universally across all Antigravity interactions in this workspace.

---

## 1. Absolute Prohibition on Reading Secrets

Antigravity agents MUST NEVER open, read, print, grep, inspect, or transfer files containing sensitive secrets or private credentials:

- **Environment & Deploy Secrets**:
  - `.env`, `.env.*` (except `.env.example`)
  - `scripts/DEPLOY.env` (except `scripts/DEPLOY.env.example`)
  - `.deploy-keys/`
- **Credential Stores & Certificates**:
  - `credentials/`, `.credentials`
  - `*.pem`, `*.key`, `*.p12`, `id_rsa`, `id_ed25519`
  - `**/google-service-account*.json`
  - `**/backup-sa*.json`
- **Private Financial Data**:
  - `portfolio/investor_profile.md` (personal household financial context; refer to `portfolio/investor_profile.md.example` instead)

---

## 2. Prohibition on Shell Environment & Credential Dumps

Agents MUST NEVER run commands that dump or echo secrets to terminal or logs:
- `env`, `printenv`, `export -p`, `set`, `typeset`
- `echo $SECRET_KEY`, `echo $DJANGO_SECRET_KEY`, `echo $EMAIL_HOST_PASSWORD`, `echo $GEMINI_API_KEY`
- Inline scripts reading environment dictionaries (e.g. `python -c "import os; print(os.environ)"`)
- Database dump commands on authentication tables (`python manage.py dumpdata tracker.User`, `tracker.WebAuthnCredential`)

---

## 3. Allowed References

When you need to verify or discuss configuration settings, variables, or credentials:
- Refer to `.env.example`
- Refer to `scripts/DEPLOY.env.example`
- Refer to `pftracker/settings.py`
- Refer to `portfolio/investor_profile.md.example`

---

## 4. Enforcement & Automated Interception

This policy is actively enforced at runtime by the Antigravity PreToolUse hook ([`.agents/scripts/safety_pre_tool.py`](file:///Users/phantomhive/Desktop/Atul/finance/.agents/scripts/safety_pre_tool.py)). Any tool call targeting protected paths or command patterns will be denied immediately.
