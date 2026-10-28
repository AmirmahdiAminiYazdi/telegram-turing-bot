import pytest

from bot.db import Database
from bot.tools.import_products import ImportError_, import_products, normalize


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


async def test_import_creates_then_skips_then_updates(db):
    items = [{"title": "الف", "price": 100, "features": ["x", " ", "y"], "seats": 5,
              "guarantee": "ضمانت"}]
    assert await import_products(db, items) == {"created": 1, "updated": 0, "skipped": 0}
    p = (await db.list_products())[0]
    assert p["features"] == "x\ny" and p["seats"] == 5 and p["guarantee"] == "ضمانت"
    assert p["sold"] == 0 and p["rating_count"] == 0  # داده‌ی ساختگی وارد نمی‌شود

    assert (await import_products(db, [{"title": "الف", "price": 200}]))["skipped"] == 1
    assert (await db.list_products())[0]["price"] == 100
    assert (await import_products(db, [{"title": "الف", "price": 200}], update=True))["updated"] == 1
    assert (await db.list_products())[0]["price"] == 200


async def test_invalid_item_imports_nothing(db):
    with pytest.raises(ImportError_):
        await import_products(db, [{"title": "ok", "price": 1}, {"title": "bad", "price": "12"}])
    assert await db.list_products(only_active=False) == []


def test_normalize_rules():
    with pytest.raises(ImportError_):
        normalize({"title": " ", "price": 5}, 1)
    with pytest.raises(ImportError_):
        normalize({"title": "a", "price": 5, "channel_id": "x"}, 1)
    assert normalize({"title": "a", "price": 5}, 1)["description"] == ""
