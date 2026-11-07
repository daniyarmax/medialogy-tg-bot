#!/usr/bin/env bash
# Dumps the Postgres database to a timestamped, compressed custom-format
# file in ./backups/. Reads connection info from DATABASE_URL (loaded from
# .env if present), the same env var the app itself uses.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${DATABASE_URL:?DATABASE_URL is not set (check your .env)}"

# pg_dump/pg_restore use libpq's URL scheme, which doesn't understand the
# "+asyncpg" driver suffix SQLAlchemy needs - strip it.
PG_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"

BACKUP_DIR="$(dirname "${BASH_SOURCE[0]}")/../backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/media_bot_${TIMESTAMP}.dump"

echo "Backing up database to $OUT_FILE ..."
pg_dump "$PG_URL" --format=custom --compress=9 --file="$OUT_FILE"
echo "Done: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
