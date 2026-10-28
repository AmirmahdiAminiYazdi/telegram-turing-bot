from unittest.mock import AsyncMock

import pytest

from bot.config import Settings
from bot.db import Database
from bot.services import discounts
from bot.services.fulfillment import complete_order
from bot.services.reminders import send_reminders

SETTINGS = Settings(bot_token="x", admin_ids=frozenset({1}))


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    for uid in (10, 20, 30):
        await d.upsert_user(uid, f"u{uid}", f"User {uid}")
    yield d
    await d.close()


async def _product(db, price=100_000, **kw):
    pid = await db.add_product("دوره", "d", price, kw.get("channel"), kw.get("access", "ACCESS"))
    return await db.get_product(pid)


# ---- migrations ----
async def test_migrations_run_once_and_set_version(db):
    row = await db._one("PRAGMA user_version")
    assert row["user_version"] == 2
    await db._migrate()  # دوباره اجرا بی‌اثر است
    assert (await db._one("PRAGMA user_version"))["user_version"] == 2


# ---- discounts ----
async def test_discount_percent_fixed_and_floor(db):
    pct = {"kind": "percent", "value": 25}
    fix = {"kind": "fixed", "value": 150_000}
    assert discounts.price_after(pct, 100_000) == 75_000
    assert discounts.price_after(fix, 100_000) == 0  # منفی نمی‌شود
    assert discounts.price_after({"kind": "percent", "value": 100}, 99) == 0


async def test_discount_validation(db):
    p = await _product(db)
    other = await _product(db)
    await db.create_discount("ABC", "percent", 10, max_uses=1)
    await db.create_discount("ONLYP", "percent", 10, product_id=other["id"])
    await db.create_discount("MINE", "percent", 10, owner_id=10)
    await db.create_discount("OLD", "percent", 10, days=1)
    await db._exec("UPDATE discounts SET expires_at='2000-01-01 00:00:00' WHERE code='OLD'")

    assert (await discounts.check(db, "abc", p, 20))[0]["code"] == "ABC"  # بی‌حساس به حروف
    assert (await discounts.check(db, "nope", p, 20))[1] == discounts.NOT_FOUND
    assert (await discounts.check(db, "onlyp", p, 20))[1] == discounts.WRONG_PRODUCT
    assert (await discounts.check(db, "mine", p, 20))[1] == discounts.NOT_YOURS
    assert (await discounts.check(db, "mine", p, 10))[0] is not None
    assert (await discounts.check(db, "old", p, 20))[1] == discounts.EXPIRED


async def test_reserve_discount_is_atomic_and_releasable(db):
    await db.create_discount("ONE", "fixed", 1000, max_uses=1)
    assert await db.reserve_discount("one") is True
    assert await db.reserve_discount("ONE") is False  # ظرفیت تمام
    await db.release_discount("ONE")
    assert await db.reserve_discount("ONE") is True
    p = await _product(db)
    assert (await discounts.check(db, "ONE", p, 10))[1] == discounts.EXHAUSTED


async def test_duplicate_discount_code_rejected(db):
    assert await db.create_discount("X", "percent", 5) is True
    assert await db.create_discount("x", "percent", 5) is False


# ---- complete_order ----
async def test_complete_order_delivers_exactly_once(db):
    bot = AsyncMock()
    p = await _product(db)
    oid = await db.create_order(10, p, "card")
    assert await complete_order(bot, db, SETTINGS, oid, "R1") is True
    assert await complete_order(bot, db, SETTINGS, oid, "R2") is False
    texts_sent = [c.args[1] for c in bot.send_message.await_args_list if c.args[0] == 10]
    assert sum("ACCESS" in t for t in texts_sent) == 1
    assert (await db.get_order(oid))["ref_id"] == "R1"


async def test_refunded_order_cannot_become_paid_again(db):
    bot = AsyncMock()
    p = await _product(db)
    oid = await db.create_order(10, p, "zarinpal")
    await complete_order(bot, db, SETTINGS, oid, "R")
    assert await db.refund_order(oid) is True
    assert await complete_order(bot, db, SETTINGS, oid, "R") is False  # callback تکراری درگاه
    assert (await db.get_order(oid))["status"] == "refunded"


async def test_delivery_failure_keeps_order_paid(db):
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("blocked")
    p = await _product(db)
    oid = await db.create_order(10, p, "card")
    assert await complete_order(bot, db, SETTINGS, oid) is True
    assert (await db.get_order(oid))["status"] == "paid"


# ---- referrals ----
async def test_referral_reward_once_and_only_for_new_users(db):
    bot = AsyncMock()
    p = await _product(db)
    assert await db.add_referral(20, 10) is True
    assert await db.add_referral(20, 30) is False  # معرف دوم جایگزین نمی‌شود
    assert await db.add_referral(10, 10) is False  # خودمعرفی
    assert await db.add_referral(99, 10) is True   # (کاربر ثبت‌نشده هم به‌عنوان referee مجاز؛ فقط معرف باید وجود داشته باشد)
    assert await db.add_referral(21, 12345) is False  # معرف ناموجود

    o1 = await db.create_order(20, p, "card")
    o2 = await db.create_order(20, p, "card")
    await complete_order(bot, db, SETTINGS, o1)
    await complete_order(bot, db, SETTINGS, o2)
    rewards = [c for c in bot.send_message.await_args_list if c.args[0] == 10]
    assert len(rewards) == 1 and "REF-" in rewards[0].args[1]
    code = rewards[0].args[1].split("<code>")[1].split("</code>")[0]
    d = await db.get_discount(code)
    assert d["owner_id"] == 10 and d["max_uses"] == 1 and d["value"] == 10
    assert await db.referral_stats(10) == {"invited": 2, "converted": 1}


async def test_free_order_gives_no_referral_reward(db):
    bot = AsyncMock()
    p = await _product(db)
    await db.add_referral(20, 10)
    oid = await db.create_order(20, p, "card", amount=0)
    await complete_order(bot, db, SETTINGS, oid)
    assert not [c for c in bot.send_message.await_args_list if c.args[0] == 10]


# ---- reminders ----
async def test_reminders_once_and_skip_buyers(db):
    bot = AsyncMock()
    p = await _product(db)
    old = await db.create_order(10, p, "card")
    fresh = await db.create_order(20, p, "card")
    bought = await db.create_order(30, p, "card")
    paid = await db.create_order(30, p, "card")
    await db._exec("UPDATE orders SET created_at=datetime('now','-3 hours') WHERE id IN (?,?,?)",
                   (old, bought, paid))
    await db.mark_paid(paid)

    assert await send_reminders(bot, db) == 1  # فقط کاربر ۱۰
    assert bot.send_message.await_args_list[0].args[0] == 10
    assert await send_reminders(bot, db) == 0  # تکرار نمی‌شود
    del fresh


# ---- reports ----
async def test_sources_report_and_revenue(db):
    await db.upsert_user(40, None, "S", "ads")
    p = await _product(db)
    oid = await db.create_order(40, p, "card")
    await db.mark_paid(oid)
    rep = {r["source"]: r for r in await db.sources_report()}
    assert rep["ads"]["users"] == 1 and rep["ads"]["paid"] == 1
    assert await db.revenue_since(7) == 100_000
