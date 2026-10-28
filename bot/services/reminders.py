from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from bot import texts
from bot.db import Database

log = logging.getLogger(__name__)


async def send_reminders(bot: Bot, db: Database) -> int:
    """به هر کاربر برای هر دوره‌ی رهاشده فقط یک‌بار یادآوری می‌فرستد."""
    sent = 0
    for o in await db.due_reminders():
        await db.mark_reminded(o["user_id"], o["product_id"])  # اول علامت بزن تا تکرار نشود
        try:
            await bot.send_message(
                o["user_id"], texts.REMINDER.format(title=escape(o["title"])),
                reply_markup=Kb(inline_keyboard=[[
                    Btn(text="🛒 ادامه خرید", callback_data=f"p:{o['product_id']}")]]))
            sent += 1
        except Exception:  # کاربر ربات را بلاک کرده و ...
            log.info("reminder to %s failed", o["user_id"])
        await asyncio.sleep(0.05)
    return sent


async def reminder_loop(bot: Bot, db: Database, interval: int = 600) -> None:
    while True:
        try:
            await send_reminders(bot, db)
        except Exception:
            log.exception("reminder loop error")
        await asyncio.sleep(interval)
