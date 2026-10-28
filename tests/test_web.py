from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db import Database
from bot.web import make_app


@pytest.fixture
async def env():
    db = Database(":memory:")
    await db.connect()
    await db.upsert_user(5, "u", "U")
    pid = await db.add_product("دوره", "d", 50000, None, "ACCESS-TEXT")
    product = await db.get_product(pid)
    oid = await db.create_order(5, product, "zarinpal")
    await db.set_authority(oid, "AUTH1")
    bot = AsyncMock()
    zp = AsyncMock()
    zp.verify.return_value = "REF9"
    settings = Settings(bot_token="x", admin_ids=frozenset({1}))
    app = make_app(db, bot, settings, zp)
    app["bot_username"] = "mybot"
    client = TestClient(TestServer(app))
    await client.start_server()
    yield client, db, bot, zp, oid
    await client.close()
    await db.close()


async def test_success_delivers_once(env):
    client, db, bot, zp, oid = env
    r = await client.get("/pay/callback?Authority=AUTH1&Status=OK")
    assert r.status == 200 and "پرداخت موفق" in await r.text()
    r = await client.get("/pay/callback?Authority=AUTH1&Status=OK")  # رفرش
    assert "پرداخت موفق" in await r.text()
    assert zp.verify.await_count == 1
    sent = [c.args[1] for c in bot.send_message.await_args_list]
    assert sum("ACCESS-TEXT" in t for t in sent) == 1
    assert (await db.get_order(oid))["status"] == "paid"
    assert (await db.get_order(oid))["ref_id"] == "REF9"


async def test_cancelled_payment(env):
    client, db, bot, zp, oid = env
    r = await client.get("/pay/callback?Authority=AUTH1&Status=NOK")
    assert "پرداخت ناموفق" in await r.text()
    zp.verify.assert_not_awaited()
    assert (await db.get_order(oid))["status"] == "pending"


async def test_verify_failure(env):
    client, db, bot, zp, oid = env
    zp.verify.return_value = None
    r = await client.get("/pay/callback?Authority=AUTH1&Status=OK")
    assert "پرداخت ناموفق" in await r.text()
    assert (await db.get_order(oid))["status"] == "pending"
    bot.send_message.assert_not_awaited()


async def test_unknown_authority(env):
    client, *_ = env
    r = await client.get("/pay/callback?Authority=NOPE&Status=OK")
    assert "پرداخت ناموفق" in await r.text()
