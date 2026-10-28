"""ابزار مشترک تست‌های جریان: Bot جعلی، ساخت Ctx با سیم‌کشی تولید، و شبیه‌ساز پیام/کالبک."""
from datetime import datetime

from aiogram import Bot
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    EditMessageCaption,
    EditMessageText,
    GetChatMember,
    GetMe,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberLeft,
    ChatMemberMember,
    Message,
    MessageId,
    PhotoSize,
    Update,
    User,
)

from bot.app import create_dispatcher
from bot.config import Settings
from bot.db import Database

ADMIN, BUYER = 99, 7


class FakeBot(Bot):
    def __init__(self):
        super().__init__("123456:TEST")
        self.calls: list[tuple[str, dict]] = []
        self.member_status = "member"

    async def __call__(self, method, request_timeout=None):
        name = type(method).__name__
        self.calls.append((name, method.model_dump()))
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot", username="mybot")
        if isinstance(method, GetChatMember):
            u = User(id=method.user_id, is_bot=False, first_name="x")
            return (ChatMemberMember(user=u) if self.member_status == "member"
                    else ChatMemberLeft(user=u))
        if isinstance(method, CopyMessage):
            return MessageId(message_id=500)
        if isinstance(method, (EditMessageText, EditMessageCaption, AnswerCallbackQuery)):
            return True
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"))

    def texts(self, chat_id=None) -> list[str]:
        return [str(p.get("text") or p.get("caption")) for n, p in self.calls
                if n in {"SendMessage", "EditMessageText", "SendPhoto", "EditMessageCaption"}
                and (chat_id is None or p.get("chat_id") == chat_id)]

    def alerts(self) -> list[str]:
        return [str(p.get("text")) for n, p in self.calls if n == "AnswerCallbackQuery" and p.get("text")]


class Ctx:
    """دسته‌ی ابزار یک تست: dispatcher، bot، db، settings و شمارنده‌ی پیام."""

    def __init__(self, dp, bot, db, settings):
        self.dp, self.bot, self.db, self.settings, self.n = dp, bot, db, settings, 0


async def make_ctx() -> Ctx:
    db = Database(":memory:")
    await db.connect()
    settings = Settings(bot_token="x", admin_ids={ADMIN}, card_number="6037-1234",
                        card_holder="Ali", support_username="sup", throttle_seconds=0)
    return Ctx(create_dispatcher(db, settings, None), FakeBot(), db, settings)  # سیم‌کشی تولید


def _entities(text):
    return ([{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/") else None)


async def say(c, uid, text):
    c.n += 1
    u = User(id=uid, is_bot=False, first_name="T", username=f"u{uid}")
    msg = Message(message_id=c.n, date=datetime.now(), chat=Chat(id=uid, type="private"),
                  from_user=u, text=text, entities=_entities(text))
    await c.dp.feed_update(c.bot, Update(update_id=c.n, message=msg))


async def photo(c, uid):
    c.n += 1
    u = User(id=uid, is_bot=False, first_name="T")
    msg = Message(message_id=c.n, date=datetime.now(), chat=Chat(id=uid, type="private"),
                  from_user=u, photo=[PhotoSize(file_id="F", file_unique_id="U", width=1, height=1)])
    await c.dp.feed_update(c.bot, Update(update_id=c.n, message=msg))


async def tap(c, uid, data, caption=None):
    c.n += 1
    u = User(id=uid, is_bot=False, first_name="T")
    host = Message(message_id=c.n, date=datetime.now(), chat=Chat(id=uid, type="private"),
                   from_user=User(id=1, is_bot=True, first_name="B"),
                   text=None if caption else "menu", caption=caption)
    cb = CallbackQuery(id=str(c.n), from_user=u, chat_instance="x", message=host, data=data)
    await c.dp.feed_update(c.bot, Update(update_id=c.n, callback_query=cb))


async def _product(c, price=100_000):
    pid = await c.db.add_product("دوره‌ی تست", "توضیح", price, None, "LINK-123")
    return pid


