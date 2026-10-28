from __future__ import annotations

import logging
from html import escape

from aiogram import Bot

from bot.db import Database

log = logging.getLogger(__name__)


async def build_access_message(bot: Bot, db: Database, order: dict,
                               admin_ids: frozenset[int] = frozenset()) -> str:
    """متن تحویل دوره: لینک یک‌بارمصرف کانال + متن دسترسی ثابت + کد لایسنس."""
    product = await db.get_product(order["product_id"])
    parts = [f"✅ دسترسی به دوره <b>{escape(product['title'])}</b>:"]

    if product["channel_id"]:
        try:
            link = await bot.create_chat_invite_link(
                product["channel_id"], member_limit=1,
                name=f"order {order['id']}")
            parts.append(f"🔗 لینک ورود (یک‌بارمصرف):\n{link.invite_link}")
        except Exception:  # ربات ادمین کانال نیست، کانال اشتباه است و ...
            log.exception("invite link failed for order %s", order["id"])
            parts.append("⚠️ ساخت لینک کانال با خطا روبه‌رو شد؛ پشتیبانی به‌زودی "
                         "لینک را برایتان می‌فرستد.")
            await _notify_admins_failure(bot, admin_ids, order)

    if await _has_codes(db, product["id"]):
        code = await db.claim_code(product["id"], order["id"])
        if code:
            parts.append(f"🔑 کد دسترسی شما:\n<code>{escape(code)}</code>")
        else:
            parts.append("⚠️ کد شما در حال آماده‌سازی است و توسط پشتیبانی ارسال می‌شود.")
            await _notify_admins_failure(bot, admin_ids, order, "کدهای دوره تمام شده است")

    if product["access_text"]:
        parts.append(escape(product["access_text"]))

    if len(parts) == 1:
        parts.append("جزئیات دسترسی توسط پشتیبانی برایتان ارسال می‌شود.")
    return "\n\n".join(parts)


async def _has_codes(db: Database, product_id: int) -> bool:
    row = await db._one("SELECT 1 FROM codes WHERE product_id=? LIMIT 1", (product_id,))
    return row is not None


async def _notify_admins_failure(bot: Bot, admin_ids: frozenset[int], order: dict,
                                 reason: str = "") -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"⚠️ تحویل سفارش #{order['id']} کامل نشد. {reason}\n"
                f"کاربر: {order['user_id']}")
        except Exception:
            log.exception("admin notify failed")


async def deliver(bot: Bot, db: Database, order: dict,
                  admin_ids: frozenset[int] = frozenset()) -> None:
    text = await build_access_message(bot, db, order, admin_ids)
    await bot.send_message(order["user_id"], text, disable_web_page_preview=True)
