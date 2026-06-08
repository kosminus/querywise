#!/usr/bin/env bash
#
# Restore an encrypted backup produced by backup.sh.
#
#   <file>.dump.enc  ->  AES-256 decrypt  ->  pg_restore --clean --if-exists
#
# DESTRUCTIVE: drops and recreates the objects in the target database. Guarded
# behind RESTORE_CONFIRM=yes. After restoring, run the app's migrations to make
# sure the schema matches the running code (`alembic upgrade head`, or just
# redeploy — the Helm migrate hook does it).
#
# Required env:
#   DATABASE_URL        target database (postgresql+asyncpg://… or postgresql://…)
#   BACKUP_PASSPHRASE   the passphrase the backup was encrypted with
#   RESTORE_CONFIRM=yes acknowledge that this overwrites the target
# Usage:
#   RESTORE_CONFIRM=yes ./restore.sh ./backups/querywise-20260608T030000Z.dump.enc
set -euo pipefail

FILE="${1:-}"
: "${DATABASE_URL:?set DATABASE_URL}"
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
[[ -n "$FILE" ]] || { echo "usage: restore.sh <backup-file.dump.enc>" >&2; exit 2; }
[[ -f "$FILE" ]] || { echo "ERROR: no such file: $FILE" >&2; exit 2; }

if [[ "${RESTORE_CONFIRM:-}" != "yes" ]]; then
  echo "This will OVERWRITE the database at the configured DATABASE_URL." >&2
  echo "Re-run with RESTORE_CONFIRM=yes to proceed." >&2
  exit 1
fi

command -v pg_restore >/dev/null || { echo "ERROR: pg_restore not found (install the postgresql client)" >&2; exit 1; }
command -v openssl >/dev/null || { echo "ERROR: openssl not found" >&2; exit 1; }

PG_URL="${DATABASE_URL/+asyncpg/}"

echo "Restoring ${FILE} -> database ..."
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$FILE" \
  | pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$PG_URL"

echo "Restore complete."
echo "Next: ensure the schema is current — 'alembic upgrade head' or redeploy."
