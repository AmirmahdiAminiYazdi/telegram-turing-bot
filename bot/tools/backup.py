"""پشتیبان‌گیری امن از SQLite با sqlite3 backup API (حتی وقتی ربات روشن است).

    python -m bot.tools.backup [--out backups] [--keep 14] [--loop 86400]

بعد از هر نسخه integrity_check اجرا می‌شود و نسخه‌های قدیمی‌تر از --keep حذف می‌شوند.
بازیابی: ربات را متوقف کن، فایل پشتیبان را جای DB_PATH کپی کن، دوباره روشن کن.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

PREFIX = "bot-"
SUFFIX = ".sqlite3"


def make_backup(db_path: str, out_dir: str, keep: int = 14, now: datetime | None = None) -> Path:
    src_path = Path(db_path)
    if not src_path.exists():
        raise FileNotFoundError(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    dest = out / f"{PREFIX}{stamp}{SUFFIX}"
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if result != "ok":
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"integrity_check failed: {result}")
    prune(out, keep)
    return dest


def prune(out_dir: Path, keep: int) -> list[Path]:
    files = sorted(out_dir.glob(f"{PREFIX}*{SUFFIX}"))
    old = files[: max(len(files) - max(keep, 1), 0)]
    for f in old:
        f.unlink()
    return old


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "data/bot.sqlite3"))
    ap.add_argument("--out", default=os.environ.get("BACKUP_DIR", "backups"))
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--loop", type=int, default=0, help="تکرار هر N ثانیه (برای سرویس کنار ربات)")
    args = ap.parse_args()
    while True:
        try:
            print("backup:", make_backup(args.db, args.out, args.keep), flush=True)
        except Exception as exc:
            print("backup FAILED:", exc, flush=True)
            if not args.loop:
                raise SystemExit(1) from exc
        if not args.loop:
            return
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
