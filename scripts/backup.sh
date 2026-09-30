#!/usr/bin/env sh
# Nightly pg_dump with 7 daily and 4 weekly copies (BAK-001). Runs inside the db image.
set -eu
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_HOUR:=2}"
export PGPASSWORD="$(cat "$PGPASSWORD_FILE")"

run_backup() {
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  tmp="$BACKUP_DIR/.energy-$stamp.dump.partial"
  pg_dump -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$tmp"
  mv "$tmp" "$BACKUP_DIR/energy-$stamp.dump"
  # Sunday dumps are also kept as weeklies.
  if [ "$(date -u +%u)" = "7" ]; then
    cp "$BACKUP_DIR/energy-$stamp.dump" "$BACKUP_DIR/weekly-energy-$stamp.dump"
  fi
  ls -1t "$BACKUP_DIR"/energy-*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f
  ls -1t "$BACKUP_DIR"/weekly-energy-*.dump 2>/dev/null | tail -n +5 | xargs -r rm -f
  date -u +%Y-%m-%dT%H:%M:%SZ > "$BACKUP_DIR/last_success"
  echo "backup ok: energy-$stamp.dump"
}

if [ "${1:-}" = "--once" ]; then
  run_backup
  exit 0
fi

while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${BACKUP_HOUR}:00" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  run_backup || echo "backup FAILED" >&2
done
