"""زیرساخت: FSM ماندگار، ادمین اولیه با /claim، سلامت سرویس، پیکربندی."""
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiohttp.test_utils import TestClient, TestServer

from bot.app import create_dispatcher
from bot.config import Settings, load_settings, parse_ids
from bot.db import Database
from bot.handlers.setup import MAX_ATTEMPTS, ClaimGate
from bot.storage import SqliteStorage
from bot.web import make_app
from tests.helpers import Ctx, FakeBot, say, tap


# ---- config ----
def test_parse_ids_and_validation():
    assert parse_ids(" 1, 22 ,,-100333") == {1, 22, -100333}
    with pytest.raises(RuntimeError, match="ADMIN_IDS"):
        parse_ids("12,abc")


GOOD = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


def test_load_settings_validates_token_and_normalizes():
    s = load_settings({"BOT_TOKEN": GOOD, "ADMIN_IDS": "5,6", "SUPPORT_USERNAME": "@sup",
                       "PUBLIC_BASE_URL": "https://x.ir/", "ZARINPAL_MERCHANT_ID": "m"})
    assert s.admin_ids == {5, 6} and s.support_username == "sup"
    assert s.public_base_url == "https://x.ir" and s.zarinpal_enabled
    for bad in ("", "nonsense", "123:short"):
        with pytest.raises(RuntimeError):
            load_settings({"BOT_TOKEN": bad})


# ---- storage ----
@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


KEY = StorageKey(bot_id=1, chat_id=2, user_id=3)


async def test_storage_roundtrip_and_isolation(db):
    st = SqliteStorage(db)
    assert await st.get_state(KEY) is None and await st.get_data(KEY) == {}
    await st.set_state(KEY, State("step", "Group"))
    await st.set_data(KEY, {"x": "فارسی", "n": 5})
    other = StorageKey(bot_id=1, chat_id=9, user_id=9)
    assert await st.get_state(KEY) == "Group:step"
    assert await st.get_data(KEY) == {"x": "فارسی", "n": 5}
    assert await st.get_state(other) is None
    await st.update_data(KEY, {"y": 1})
    assert (await st.get_data(KEY))["y"] == 1
    await st.set_state(KEY, None)
    await st.set_data(KEY, {})
    assert await st.get_state(KEY) is None
    assert await db.fsm_get("1:2:3:None:None:default") is None  # ردیف خالی پاک می‌شود


async def test_fsm_survives_restart(tmp_path):
    path = str(tmp_path / "b.sqlite3")
    d1 = Database(path)
    await d1.connect()
    await SqliteStorage(d1).set_state(KEY, "S:1")
    await d1.close()
    d2 = Database(path)  # شبیه ری‌استارت
    await d2.connect()
    assert await SqliteStorage(d2).get_state(KEY) == "S:1"
    await d2.close()


# ---- /claim ----
def test_claim_gate_locks_after_failures():
    t = {"now": 0.0}
    g = ClaimGate("secret-code", clock=lambda: t["now"])
    for _ in range(MAX_ATTEMPTS):
        assert g.try_claim("wrong") is False
    assert g.try_claim("secret-code") is False  # قفل است حتی با کد درست
    t["now"] = 10_000
    assert g.try_claim("secret-code") is True


async def test_first_admin_claim_flow(db):
    settings = Settings(bot_token="x", admin_ids=set(), throttle_seconds=0)
    gate = ClaimGate("CODE123")
    dp = create_dispatcher(db, settings, None, gate)
    bot = FakeBot()
    c = Ctx(dp, bot, db, settings)

    await say(c, 5, "/admin")
    assert not any("پنل ادمین" in t for t in bot.texts(5))  # هنوز ادمین نیست
    await say(c, 5, "/claim wrong")
    assert any("معتبر نیست" in t for t in bot.texts(5)) and 5 not in settings.admin_ids
    await say(c, 5, "/claim CODE123")
    assert 5 in settings.admin_ids
    assert await db.get_setting("extra_admins") == "5"  # برای ری‌استارت ذخیره شد
    await say(c, 5, "/admin")
    assert any("پنل ادمین" in t for t in bot.texts(5))
    await say(c, 6, "/claim CODE123")  # بعد از ادمین شدن، فرمان دیگر کار نمی‌کند
    assert 6 not in settings.admin_ids


# ---- error handler ----
async def test_unhandled_error_notifies_admin_once(db, monkeypatch):
    settings = Settings(bot_token="x", admin_ids={99}, throttle_seconds=0)
    dp = create_dispatcher(db, settings, None)
    bot = FakeBot()
    c = Ctx(dp, bot, db, settings)

    async def boom(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(Database, "list_products", boom)
    await say(c, 7, "/start")
    await tap(c, 7, "catalog")
    await tap(c, 7, "catalog")
    alerts = [t for t in bot.texts(99) if "خطای ربات" in t]
    assert len(alerts) == 1 and "RuntimeError" in alerts[0]  # طوفان خطا اسپم نمی‌شود


# ---- health ----
async def test_health_endpoint_and_callback_without_zarinpal(db):
    app = make_app(db, AsyncMock(), Settings(bot_token="x"), None)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.get("/health")
        assert r.status == 200 and (await r.json()) == {"ok": True}
        assert (await client.get("/pay/callback?Authority=A&Status=OK")).status == 404
    finally:
        await client.close()
