from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.services.delivery import deliver
from bot.services.zarinpal import Zarinpal, ZarinpalError

log = logging.getLogger(__name__)
router = Router(name="user")


async def _show_product(msg: Message, db: Database, product_id: int, edit: bool) -> None:
    p = await db.get_product(product_id)
    if not p or not p["active"]:
        await msg.answer(texts.NO_PRODUCTS)
        return
    text = texts.PRODUCT_CARD.format(
        title=escape(p["title"]), description=escape(p["description"]),
        price=kb.fmt_price(p["price"]))
    markup = kb.product(p["id"])
    if edit:
        await msg.edit_text(text, reply_markup=markup)
    else:
        await msg.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, db: Database) -> None:
    u = message.from_user
    payload = (command.args or "").strip()
    await db.upsert_user(u.id, u.username, u.full_name, payload or None)
    if payload.startswith("p_") and payload[2:].isdigit():  # لینک مستقیم به دوره
        await _show_product(message, db, int(payload[2:]), edit=False)
        return
    await message.answer(texts.WELCOME.format(name=escape(u.first_name)),
                         reply_markup=kb.main_menu())


@router.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        texts.WELCOME.format(name=escape(cb.from_user.first_name)),
        reply_markup=kb.main_menu())
    await cb.answer()


@router.callback_query(F.data == "catalog")
async def catalog(cb: CallbackQuery, db: Database) -> None:
    products = await db.list_products()
    if not products:
        await cb.message.edit_text(texts.NO_PRODUCTS, reply_markup=kb.main_menu())
    else:
        await cb.message.edit_text(texts.CATALOG_TITLE, reply_markup=kb.catalog(products))
    await cb.answer()


@router.callback_query(F.data.startswith("p:"))
async def product(cb: CallbackQuery, db: Database) -> None:
    await _show_product(cb.message, db, int(cb.data.split(":")[1]), edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    product_id = int(cb.data.split(":")[1])
    p = await db.get_product(product_id)
    if not p or not p["active"]:
        await cb.answer(texts.NO_PRODUCTS, show_alert=True)
        return
    owned = await db.paid_order(cb.from_user.id, product_id)
    if owned:
        await cb.message.answer(texts.ALREADY_OWNED)
        await deliver(bot, db, owned, settings.admin_ids)
        await cb.answer()
        return
    if not (settings.zarinpal_enabled or settings.card_enabled):
        await cb.answer(texts.NO_METHODS, show_alert=True)
        return
    await cb.message.edit_text(
        texts.PRODUCT_CARD.format(
            title=escape(p["title"]), description=escape(p["description"]),
            price=kb.fmt_price(p["price"])) + "\n\n" + texts.CHOOSE_METHOD,
        reply_markup=kb.methods(product_id, settings.zarinpal_enabled,
                                settings.card_enabled))
    await cb.answer()


@router.callback_query(F.data.startswith("pay:z:"))
async def pay_online(cb: CallbackQuery, db: Database, settings: Settings,
                     zarinpal: Zarinpal | None) -> None:
    if not (settings.zarinpal_enabled and zarinpal):
        await cb.answer(texts.NO_METHODS, show_alert=True)
        return
    p = await db.get_product(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        await cb.answer(texts.NO_PRODUCTS, show_alert=True)
        return
    order_id = await db.create_order(cb.from_user.id, p, "zarinpal")
    try:
        authority, url = await zarinpal.request(
            p["price"], f"{settings.public_base_url}/pay/callback",
            f"سفارش {order_id} - {p['title']}")
    except ZarinpalError:
        log.exception("zarinpal request failed")
        await cb.answer(texts.ZARINPAL_FAIL, show_alert=True)
        return
    await db.set_authority(order_id, authority)
    await cb.message.edit_text(texts.ZARINPAL_PAY.format(order_id=order_id),
                               reply_markup=kb.pay_link(url))
    await cb.answer()


@router.callback_query(F.data.startswith("pay:c:"))
async def pay_card(cb: CallbackQuery, db: Database, settings: Settings) -> None:
    if not settings.card_enabled:
        await cb.answer(texts.NO_METHODS, show_alert=True)
        return
    p = await db.get_product(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        await cb.answer(texts.NO_PRODUCTS, show_alert=True)
        return
    order_id = await db.create_order(cb.from_user.id, p, "card")
    holder = f"به نام {escape(settings.card_holder)}" if settings.card_holder else ""
    await cb.message.edit_text(texts.CARD_INFO.format(
        order_id=order_id, price=kb.fmt_price(p["price"]),
        card=escape(settings.card_number), holder=holder))
    await cb.answer()


@router.message(F.photo)
async def receipt(message: Message, db: Database, settings: Settings, bot: Bot) -> None:
    """عکس رسید به آخرین سفارش کارت‌به‌کارت باز کاربر وصل می‌شود."""
    order = await db._one(
        "SELECT * FROM orders WHERE user_id=? AND method='card'"
        " AND status IN ('pending','receipt_sent') ORDER BY id DESC LIMIT 1",
        (message.from_user.id,))
    if not order:
        await message.answer(texts.NO_ACTIVE_ORDER)
        return
    file_id = message.photo[-1].file_id
    await db.set_receipt(order["id"], file_id)
    await message.answer(texts.RECEIPT_RECEIVED)
    p = await db.get_product(order["product_id"])
    caption = (f"🧾 رسید جدید\nسفارش #{order['id']}\nدوره: {escape(p['title'])}\n"
               f"مبلغ: {kb.fmt_price(order['amount'])} تومان\n"
               f"کاربر: {message.from_user.full_name} (<code>{message.from_user.id}</code>)")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_photo(admin_id, file_id, caption=caption,
                                 reply_markup=kb.receipt_review(order["id"]))
        except Exception:
            log.exception("cannot notify admin %s", admin_id)


@router.callback_query(F.data == "mine")
async def mine(cb: CallbackQuery, db: Database) -> None:
    orders = await db.user_paid_orders(cb.from_user.id)
    if not orders:
        await cb.message.edit_text(texts.MY_COURSES_EMPTY, reply_markup=kb.main_menu())
    else:
        await cb.message.edit_text(texts.MY_COURSES, reply_markup=kb.mine(orders))
    await cb.answer()


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    order = await db.get_order(int(cb.data.split(":")[1]))
    if not order or order["user_id"] != cb.from_user.id or order["status"] != "paid":
        await cb.answer()
        return
    await deliver(bot, db, order, settings.admin_ids)
    await cb.answer()


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery, settings: Settings) -> None:
    text = (texts.SUPPORT.format(username=settings.support_username)
            if settings.support_username else texts.SUPPORT_NONE)
    await cb.message.edit_text(text, reply_markup=kb.main_menu())
    await cb.answer()


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer("برای شروع /start را بزن.")
