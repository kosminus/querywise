#!/usr/bin/env bash
#
# Encrypted logical backup of the QueryWise app database.
#
#   pg_dump (custom format)  ->  AES-256 (openssl, PBKDF2)  ->  <dir>/querywise-<ts>.dump.enc
#
# Runs anywhere with a postgres client + openssl and reachability to the DB:
# a cron host, a CI job, or `kubectl exec` into a pod. Decrypt/restore with
# restore.sh using the same passphrase.
#
# Required env:
#   DATABASE_URL          postgresql+asyncpg://… or postgresql://… (driver suffix stripped)
#   BACKUP_PASSPHRASE     symmetric key for encryption — store in your secret manager
# Optional env:
#   BACKUP_DIR            output directory          (default ./backups)
#   BACKUP_RETENTION_DAYS prune local dumps older than N days (default 14; 0 = keep all)
#   BACKUP_S3_URI         s3://bucket/prefix    -> uploaded with `aws`
#   BACKUP_GCS_URI        gs://bucket/prefix    -> uploaded with `gcloud storage`
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"

command -v pg_dump >/dev/null || { echo "ERROR: pg_dump not found (install the postgresql client)" >&2; exit 1; }
command -v openssl >/dev/null || { echo "ERROR: openssl not found" >&2; exit 1; }

# pg_dump speaks plain postgresql:// — drop the SQLAlchemy +asyncpg driver suffix.
PG_URL="${DATABASE_URL/+asyncpg/}"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/querywise-${TS}.dump.enc"

echo "Backing up database -> ${OUT}"
pg_dump --format=custom --no-owner --no-privileges "$PG_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE \
  > "$OUT"

echo "Wrote $(du -h "$OUT" | cut -f1) encrypted backup."

# Optional offsite upload.
if [[ -n "${BACKUP_S3_URI:-}" ]]; then
  echo "Uploading to ${BACKUP_S3_URI%/}/$(basename "$OUT")"
  aws s3 cp "$OUT" "${BACKUP_S3_URI%/}/$(basename "$OUT")"
fi
if [[ -n "${BACKUP_GCS_URI:-}" ]]; then
  echo "Uploading to ${BACKUP_GCS_URI%/}/$(basename "$OUT")"
  gcloud storage cp "$OUT" "${BACKUP_GCS_URI%/}/$(basename "$OUT")"
fi

# Prune old local backups.
if [[ "$RETENTION" -gt 0 ]]; then
  find "$BACKUP_DIR" -name 'querywise-*.dump.enc' -type f -mtime +"$RETENTION" -print -delete
fi

echo "Done."
