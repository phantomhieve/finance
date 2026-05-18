#!/bin/bash
set -euo pipefail

BACKUP_SA="/path/to/app/credentials/backup-sa.json"
BUCKET="postgres_backup_cash_center"
DATABASES="vault_db cashcenter familytree"
STAMP=$(date +%Y-%m-%d_%H-%M-%S)
TMPDIR=$(mktemp -d /tmp/pg_backup.XXXXXX)
LOGFILE="/var/log/vault/backup.log"
VENV="/path/to/app/venv/bin/python3"
ZIP_NAME="${STAMP}.zip"
ZIP_PATH="${TMPDIR}/${ZIP_NAME}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"; }

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

log "=== Backup started ==="

FAILED=0
for DB in $DATABASES; do
  DUMP_FILE="${TMPDIR}/${DB}.sql"

  log "Dumping ${DB}..."
  if ! sudo -u postgres pg_dump --no-owner --no-privileges -d "$DB" > "$DUMP_FILE" 2>>"$LOGFILE"; then
    log "ERROR: pg_dump failed for ${DB}"
    FAILED=1
    continue
  fi

  ROWS=$(wc -l < "$DUMP_FILE")
  log "  pg_dump OK (${ROWS} lines)"
done

if [ "$FAILED" -ne 0 ]; then
  log "=== Aborting — pg_dump failures ==="
  exit 1
fi

log "Creating ${ZIP_NAME}..."
cd "$TMPDIR"
zip -9 "$ZIP_PATH" *.sql >>"$LOGFILE" 2>&1
SIZE=$(du -h "$ZIP_PATH" | cut -f1)
log "  zip: ${SIZE}"

log "Uploading to gs://${BUCKET}/${ZIP_NAME}..."
if ! $VENV - "$BACKUP_SA" "$BUCKET" "$ZIP_PATH" "$ZIP_NAME" <<'PYEOF'
import sys
from google.cloud import storage
sa_path, bucket_name, local_path, gcs_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
client = storage.Client.from_service_account_json(sa_path)
bucket = client.bucket(bucket_name)
blob = bucket.blob(gcs_path)
blob.upload_from_filename(local_path)
print(f"  uploaded: gs://{bucket_name}/{gcs_path}")
PYEOF
then
  log "ERROR: upload failed"
  exit 1
fi

log "=== Backup complete: ${ZIP_NAME} (${SIZE}) ==="
