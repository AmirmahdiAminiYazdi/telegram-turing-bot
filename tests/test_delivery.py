from unittest.mock import AsyncMock

import pytest
from aiogram.types import ChatInviteLink, User

from bot.db import Database
from bot.services.delivery import build_access_message


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    await d.upsert_user(10, "u", "U")
    yield d
    await d.close()


def _bot(link="https://t.me/+abc", fail=False):
    bot = AsyncMock()
    if fail:
        bot.create_chat_invite_link.side_effect = RuntimeError("not admin")
    else:
        bot.create_chat_invite_link.return_value = ChatInviteLink(
            invite_link=link, creator=User(id=1, is_bot=True, first_name="b"),
            creates_join_request=False, is_primary=False, is_revoked=False)
    return bot


async def _order(db, channel=None, access=None, codes=()):
    pid = await db.add_product("دوره <x>", "d", 1000, channel, access)
    if codes:
        await db.add_codes(pid, list(codes))
    oid = await db.create_order(10, await db.get_product(pid), "card")
    return await db.get_order(oid)


async def test_single_use_invite_link_is_requested(db):
    bot = _bot()
    order = await _order(db, channel=-1001)
    text = await build_access_message(bot, db, order)
    bot.create_chat_invite_link.assert_awaited_once()
    kwargs = bot.create_chat_invite_link.await_args.kwargs
    assert kwargs["member_limit"] == 1
    assert "https://t.me/+abc" in text and "&lt;x&gt;" in text  # عنوان escape شده


async def test_invite_failure_degrades_and_alerts_admins(db):
    bot = _bot(fail=True)
    order = await _order(db, channel=-1001, access="LINK")
    text = await build_access_message(bot, db, order, {7})
    assert "ساخت لینک کانال با خطا" in text and "LINK" in text  # بقیه‌ی دسترسی از دست نمی‌رود
    assert bot.send_message.await_args.args[0] == 7


async def test_license_codes_are_distinct_and_stable_per_order(db):
    bot = _bot()
    o1 = await _order(db, codes=["K1", "K2"])
    pid = o1["product_id"]
    o2_id = await db.create_order(10, await db.get_product(pid), "card")
    o2 = await db.get_order(o2_id)
    t1 = await build_access_message(bot, db, o1)
    t1_again = await build_access_message(bot, db, o1)
    t2 = await build_access_message(bot, db, o2)
    assert "K1" in t1 and "K1" in t1_again and "K2" in t2


async def test_codes_exhausted_warns_user_and_admin(db):
    bot = _bot()
    o1 = await _order(db, codes=["ONLY"])
    pid = o1["product_id"]
    o2 = await db.get_order(await db.create_order(10, await db.get_product(pid), "card"))
    await build_access_message(bot, db, o1)
    text = await build_access_message(bot, db, o2, {7})
    assert "در حال آماده‌سازی" in text
    assert "تمام شده" in bot.send_message.await_args.args[1]


async def test_product_without_any_access_info_falls_back(db):
    text = await build_access_message(_bot(), db, await _order(db))
    assert "پشتیبانی" in text
