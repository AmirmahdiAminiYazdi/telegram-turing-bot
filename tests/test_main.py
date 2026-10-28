"""راه‌اندازی کامل main با Bot جعلی: توکن، ادمین اولیه، سرور HTTP و خاموشی تمیز."""
import logging
import socket

import pytest
from aiogram import Dispatcher

import bot.main as main_mod
from tests.helpers import FakeBot

TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Bot(FakeBot):
    def __init__(self, token, default=None):
        super().__init__()


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k, v in {"BOT_TOKEN": TOKEN, "DB_PATH": str(tmp_path / "b.sqlite3"),
                 "WEB_HOST": "127.0.0.1", "WEB_PORT": str(_free_port()), "ADMIN_IDS": "",
                 "ZARINPAL_MERCHANT_ID": "", "PUBLIC_BASE_URL": ""}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(main_mod, "Bot", _Bot)
    return tmp_path


async def test_startup_without_admin_prints_claim_hint_and_shuts_down(env, monkeypatch, caplog):
    ran = {}

    async def fake_polling(self, bot, **kw):
        import aiohttp
        async with aiohttp.ClientSession() as s, s.get(
                f"http://127.0.0.1:{main_mod.load_settings().web_port}/health") as r:
            ran["health"] = (r.status, await r.json())
    monkeypatch.setattr(Dispatcher, "start_polling", fake_polling)
    with caplog.at_level(logging.INFO):
        await main_mod.main()
    assert ran["health"] == (200, {"ok": True})
    assert any("/claim " in r.getMessage() for r in caplog.records)
    assert TOKEN not in caplog.text  # توکن هرگز لاگ نمی‌شود


async def test_startup_merges_persisted_admins_and_notifies(env, monkeypatch):
    from bot.db import Database
    db = Database(str(env / "b.sqlite3"))
    await db.connect()
    await db.set_setting("extra_admins", "55")
    await db.close()
    sent = []
    orig = _Bot.__call__

    async def spy(self, method, request_timeout=None):
        if type(method).__name__ == "SendMessage":
            sent.append((method.chat_id, method.text))
        return await orig(self, method, request_timeout)
    monkeypatch.setattr(_Bot, "__call__", spy)

    async def noop(self, bot, **kw):
        return None
    monkeypatch.setattr(Dispatcher, "start_polling", noop)
    await main_mod.main()
    assert any(cid == 55 and "روشن شد" in t for cid, t in sent)


async def test_bad_token_stops_with_clear_message(env, monkeypatch):
    class Boom(_Bot):
        async def __call__(self, method, request_timeout=None):
            raise RuntimeError("Unauthorized")
    monkeypatch.setattr(main_mod, "Bot", Boom)
    with pytest.raises(SystemExit, match="توکن"):
        await main_mod.main()


async def test_invalid_config_fails_fast(env, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "garbage")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        await main_mod.main()
