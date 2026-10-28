from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup as Kb

from bot import texts
from bot.config import Settings
from bot.db import Database

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class Throttle(BaseMiddleware):
    """جلوگیری از اسپم: حداقل فاصله بین دو رویداد یک کاربر (ادمین‌ها مستثنا)."""

    def __init__(self, interval: float = 0.4, clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self.clock = clock
        self._last: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]):
        user = data.get("event_from_user")
        settings: Settings | None = data.get("settings")
        if user is None or (settings and user.id in settings.admin_ids):
            return await handler(event, data)
        now = self.clock()
        if now - self._last.get(user.id, -1e9) < self.interval:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.TOO_FAST)
            return None
        self._last[user.id] = now
        if len(self._last) > 10_000:  # جلوگیری از رشد بی‌نهایت حافظه
            cutoff = now - 60
            self._last = {k: v for k, v in self._last.items() if v > cutoff}
        return await handler(event, data)


def _channel_link(channel: str, link: str) -> str | None:
    if link:
        return link
    return f"https://t.me/{channel.lstrip('@')}" if channel.startswith("@") else None


class ForceSub(BaseMiddleware):
    """قفل عضویت: تا کاربر عضو کانال تنظیم‌شده نشود، فقط پیام عضویت می‌بیند.

    اگر ربات به کانال دسترسی نداشته باشد (ادمین نیست)، قفل را نادیده می‌گیرد تا فروش نخوابد.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]):
        user = data.get("event_from_user")
        db: Database = data["db"]
        settings: Settings = data["settings"]
        bot: Bot = data["bot"]
        channel = await db.get_setting("force_channel")
        if not channel or user is None or user.id in settings.admin_ids:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "fs:check":
            if await self._is_member(bot, channel, user.id):
                await event.answer()
                return await handler(event, data)
            await event.answer(texts.FORCE_SUB_FAIL, show_alert=True)
            return None
        if await self._is_member(bot, channel, user.id):
            return await handler(event, data)

        link = _channel_link(channel, await db.get_setting("force_channel_link"))
        rows = ([[Btn(text="📢 عضویت در کانال", url=link)]] if link else [])
        rows.append([Btn(text="✅ عضو شدم", callback_data="fs:check")])
        target = event.message if isinstance(event, CallbackQuery) else event
        if isinstance(event, CallbackQuery):
            await event.answer()
        if isinstance(target, Message):
            await target.answer(texts.FORCE_SUB, reply_markup=Kb(inline_keyboard=rows))
        return None

    @staticmethod
    async def _is_member(bot: Bot, channel: str, user_id: int) -> bool:
        try:
            chat_id: int | str = int(channel) if channel.lstrip("-").isdigit() else channel
            m = await bot.get_chat_member(chat_id, user_id)
        except Exception:
            log.warning("force-sub check failed for %s; allowing", channel)
            return True  # بدون دسترسی به کانال، فروش را متوقف نمی‌کنیم
        return m.status not in {"left", "kicked"}
