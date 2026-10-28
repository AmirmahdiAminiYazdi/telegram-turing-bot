import pytest

from bot.db import Database


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    await d.upsert_user(1, "u", "User")
    yield d
    await d.close()


async def _product(db, **kw):
    pid = await db.add_product("دوره", "توضیح", 100000, kw.get("channel"), kw.get("access"))
    return await db.get_product(pid)


async def test_mark_paid_only_once(db):
    p = await _product(db)
    oid = await db.create_order(1, p, "card")
    assert await db.mark_paid(oid, "R1") is True
    assert await db.mark_paid(oid, "R2") is False
    assert (await db.get_order(oid))["ref_id"] == "R1"


async def test_receipt_flow_and_reject(db):
    p = await _product(db)
    oid = await db.create_order(1, p, "card")
    assert await db.set_receipt(oid, "file") is True
    assert len(await db.pending_receipts()) == 1
    assert await db.reject_order(oid) is True
    assert await db.reject_order(oid) is False  # بار دوم اثر ندارد
    assert await db.pending_receipts() == []


async def test_receipt_rejected_for_online_orders(db):
    p = await _product(db)
    oid = await db.create_order(1, p, "zarinpal")
    assert await db.set_receipt(oid, "file") is False


async def test_codes_claimed_once_per_order(db):
    p = await _product(db)
    await db.add_codes(p["id"], ["A", "B"])
    o1 = await db.create_order(1, p, "card")
    o2 = await db.create_order(1, p, "card")
    assert await db.claim_code(p["id"], o1) == "A"
    assert await db.claim_code(p["id"], o1) == "A"  # تحویل مجدد همان کد
    assert await db.claim_code(p["id"], o2) == "B"
    o3 = await db.create_order(1, p, "card")
    assert await db.claim_code(p["id"], o3) is None
    assert await db.free_codes_count(p["id"]) == 0


async def test_cannot_delete_product_with_orders(db):
    p = await _product(db)
    await db.create_order(1, p, "card")
    assert await db.delete_product(p["id"]) is False
    p2 = await _product(db)
    assert await db.delete_product(p2["id"]) is True


async def test_stats(db):
    p = await _product(db)
    o = await db.create_order(1, p, "card")
    await db.create_order(1, p, "card")
    await db.mark_paid(o)
    s = await db.stats()
    assert s == {"users": 1, "orders": 2, "paid": 1, "revenue": 100000}
