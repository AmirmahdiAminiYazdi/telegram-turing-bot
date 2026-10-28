import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from bot.tools.backup import make_backup, prune


def _db(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t(x)")
    c.execute("INSERT INTO t VALUES ('فارسی')")
    c.commit()
    return c


def test_backup_is_consistent_and_readable(tmp_path):
    src = tmp_path / "bot.sqlite3"
    live = _db(src)  # اتصال باز می‌ماند، مثل ربات در حال اجرا
    dest = make_backup(str(src), str(tmp_path / "bk"))
    assert sqlite3.connect(dest).execute("SELECT x FROM t").fetchone()[0] == "فارسی"
    live.close()


def test_prune_keeps_newest(tmp_path):
    src = tmp_path / "bot.sqlite3"
    _db(src).close()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        make_backup(str(src), str(tmp_path / "bk"), keep=3, now=base + timedelta(days=i))
    names = sorted(p.name for p in (tmp_path / "bk").iterdir())
    assert len(names) == 3 and names[-1].startswith("bot-20260105")
    assert prune(tmp_path / "bk", keep=100) == []


def test_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_backup(str(tmp_path / "nope.sqlite3"), str(tmp_path / "bk"))
