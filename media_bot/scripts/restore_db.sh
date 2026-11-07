#!/usr/bin/env bash
# Restores a dump produced by backup_db.sh. Usage:
#   ./scripts/restore_db.sh backups/media_bot_20260101_120000.dump
#
# WARNING: this drops and recreates objects in the TARGET database named
# in DATABASE_URL - never point this at a database you don't intend to
# overwrite. Confirms before running.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ $# -ne 1 ]; then
  echo "Usage: $0 <dump-file>" >&2
  exit 1
fi
DUMP_FILE="$1"
if [ ! -f "$DUMP_FILE" ]; then
  echo "No such file: $DUMP_FILE" >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${DATABASE_URL:?DATABASE_URL is not set (check your .env)}"
PG_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"

echo "This will restore '$DUMP_FILE' into:"
echo "  $PG_URL"
echo "Existing objects with the same names will be dropped and recreated."
read -r -p "Continue? [y/N] " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "Aborted."
  exit 1
fi

pg_restore --clean --if-exists --no-owner --dbname="$PG_URL" "$DUMP_FILE"
echo "Restore complete."
