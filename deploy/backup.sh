#!/usr/bin/env bash
# پشتیبان‌گیری امن از SQLite (با .backup، حتی وقتی ربات روشن است). در cron روزانه بگذار.
set -euo pipefail
DB="${DB_PATH:-data/bot.sqlite3}"
OUT="${1:-backups}"
mkdir -p "$OUT"
sqlite3 "$DB" ".backup '$OUT/bot-$(date +%F).sqlite3'"
find "$OUT" -name 'bot-*.sqlite3' -mtime +14 -delete
