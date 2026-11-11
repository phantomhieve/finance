# Strict Secrets & Credential Protection Policy

This rule applies across all agent interactions in this workspace.

---

## 1. Never Read or Inspect Secret Files

Never open, read, print, grep, or transfer files containing credentials or private household data:
- **Environment & Deploy Secrets**: `.env`, `.env.*` (except `.env.example`), `scripts/DEPLOY.env` (except `scripts/DEPLOY.env.example`), `.deploy-keys/`
- **Credentials & Keys**: `credentials/`, `.credentials`, `*.pem`, `*.key`, `*.p12`, `id_rsa`, `id_ed25519`, `**/google-service-account*.json`, `**/backup-sa*.json`
- **Private Household Context**: `portfolio/investor_profile.md` (loaded at runtime by `portfolio/dag.py` — never read or delete it; inspect `portfolio/investor_profile.md.example` instead)

---

## 2. Never Dump Environment or Auth Secrets

Never execute commands or scripts that print environment variables or stored secrets:
- `env`, `printenv`, `export -p`, `set`, `typeset`
- `echo $SECRET_KEY`, `echo $DJANGO_SECRET_KEY`, `echo $EMAIL_HOST_PASSWORD`, `echo $GEMINI_API_KEY`, `echo $SHAKTI_API_KEY`, `echo $EXPENSES_ENCRYPTION_KEY`
- Inline scripts dumping `os.environ` or `manage.py dumpdata` on `tracker.User`, `tracker.WebAuthnCredential`, or `expenses.GmailAccount`

---

## 3. Safe Configuration References

Inspect variable names and defaults via:
- [`.env.example`](../../.env.example)
- [`scripts/DEPLOY.env.example`](../../scripts/DEPLOY.env.example)
- [`pftracker/settings.py`](../../pftracker/settings.py)
- [`portfolio/investor_profile.md.example`](../../portfolio/investor_profile.md.example)

---

## 4. Runtime Hook Enforcement

This policy is enforced at runtime by the PreToolUse hook ([`../scripts/safety_pre_tool.py`](../scripts/safety_pre_tool.py)).
