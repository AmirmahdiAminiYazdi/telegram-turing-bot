"""مسیر واقعی dispatcher (فیلتر ادمین، تزریق وابستگی‌ها) با Bot جعلی."""
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User

from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, user


class FakeBot(Bot):
    def __init__(self):
        super().__init__("123456:TEST")
        self.sent: list[tuple[str, dict]] = []

    async def __call__(self, method: TelegramMethod, request_timeout=None):
        self.sent.append((type(method).__name__, method.model_dump()))
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"))


@pytest.fixture
async def ctx():
    db = Database(":memory:")
    await db.connect()
    settings = Settings(bot_token="x", admin_ids=frozenset({99}), card_number="6037")
    dp = Dispatcher(storage=MemoryStorage(), db=db, settings=settings, zarinpal=None)
    dp.include_router(admin.router)
    dp.include_router(user.router)
    bot = FakeBot()
    yield dp, bot, db
    await db.close()


def _msg(uid: int, text: str, n: int = 1) -> Update:
    return Update(update_id=n, message=Message(
        message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="T"), text=text,
        entities=[{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if text.startswith("/") else None))


async def test_start_and_admin_gate(ctx):
    # روترها singleton ماژول‌اند و فقط یک‌بار به Dispatcher وصل می‌شوند؛ پس یک تست.
    dp, bot, db = ctx
    await dp.feed_update(bot, _msg(7, "/start ad_instagram"))
    assert bot.sent[-1][0] == "SendMessage"
    assert (await db._one("SELECT source FROM users WHERE id=7"))["source"] == "ad_instagram"

    await dp.feed_update(bot, _msg(7, "/admin", 2))  # کاربر عادی
    assert not any("پنل ادمین" in str(m[1].get("text")) for m in bot.sent)
    await dp.feed_update(bot, _msg(99, "/admin", 3))  # ادمین
    assert any("پنل ادمین" in str(m[1].get("text")) for m in bot.sent)
