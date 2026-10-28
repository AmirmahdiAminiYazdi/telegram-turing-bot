from __future__ import annotations

import logging
import secrets

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.services.delivery import deliver

log = logging.getLogger(__name__)

REFERRAL_DEFAULT_PERCENT = 10
REFERRAL_CODE_DAYS = 60


async def complete_order(bot: Bot, db: Database, settings: Settings, order_id: int,
                         ref_id: str | None = None) -> bool:
    """تنها مسیر تبدیل سفارش به «پرداخت‌شده»: اتمیک، تحویل فقط یک‌بار، پاداش معرف.

    True فقط برای اولین فراخوانی موفق؛ فراخوانی مجدد (رفرش درگاه، دوبار کلیک ادمین) اثری ندارد.
    """
    if not await db.mark_paid(order_id, ref_id):
        return False
    order = await db.get_order(order_id)
    try:
        await bot.send_message(order["user_id"], texts.PAID_OK)
        await deliver(bot, db, order, settings.admin_ids)
    except Exception:
        # سفارش پرداخت‌شده می‌ماند؛ کاربر از «دوره‌های من» دوباره می‌گیرد.
        log.exception("delivery failed for order %s", order_id)
    if order["amount"] > 0:
        await _reward_referrer(bot, db, order["user_id"])
        await _loyalty_offer(bot, db, order)
    return True


LOYALTY_DEFAULT_PERCENT = 10
LOYALTY_CODE_DAYS = 7


async def _loyalty_offer(bot: Bot, db: Database, order: dict) -> None:
    """بعد از خرید، برای دوره‌ی دیگری که هنوز نخریده، یک تخفیف شخصی با انقضای واقعی."""
    percent = int(await db.get_setting("loyalty_percent", str(LOYALTY_DEFAULT_PERCENT)))
    if percent <= 0:
        return
    owned = {o["product_id"] for o in await db.user_paid_orders(order["user_id"])}
    others = [p for p in await db.list_products() if p["id"] not in owned]
    if not others:
        return
    code = f"VIP-{secrets.token_hex(3).upper()}"
    await db.create_discount(code, "percent", min(percent, 100), max_uses=1,
                             days=LOYALTY_CODE_DAYS, owner_id=order["user_id"])
    try:
        await bot.send_message(
            order["user_id"],
            texts.LOYALTY.format(percent=percent, code=code, days=LOYALTY_CODE_DAYS),
            reply_markup=Kb(inline_keyboard=[[Btn(text="📚 دیدن دوره‌ها", callback_data="catalog")]]))
    except Exception:
        log.exception("loyalty offer notify failed")


async def _reward_referrer(bot: Bot, db: Database, referee_id: int) -> None:
    referrer = await db.claim_referral_reward(referee_id)
    if not referrer:
        return
    percent = int(await db.get_setting("referral_percent", str(REFERRAL_DEFAULT_PERCENT)))
    if percent <= 0:
        return
    code = f"REF-{secrets.token_hex(4).upper()}"
    await db.create_discount(code, "percent", min(percent, 100), max_uses=1,
                             days=REFERRAL_CODE_DAYS, owner_id=referrer)
    try:
        await bot.send_message(referrer, texts.REFERRAL_REWARD.format(
            percent=percent, code=code, days=REFERRAL_CODE_DAYS))
    except Exception:
        log.exception("referral reward notify failed")
