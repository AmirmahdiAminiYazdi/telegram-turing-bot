from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.services import discounts
from bot.services.delivery import deliver
from bot.services.fulfillment import complete_order
from bot.services.zarinpal import Zarinpal, ZarinpalError
from bot.states import DiscountState, SupportState

log = logging.getLogger(__name__)
router = Router(name="user")

ONLINE_MIN_TOMAN = 1000  # حداقل مبلغ زرین‌پال


# ---------- کمکی‌ها ----------
def _card_text(p: dict, price: int | None = None, code: str | None = None) -> str:
    text = texts.PRODUCT_CARD.format(
        title=escape(p["title"]), description=escape(p["description"]),
        price=kb.fmt_price(p["price"]))
    if code and price is not None:
        text += "\n\n" + texts.DISCOUNT_OK.format(
            old=kb.fmt_price(p["price"]), new=kb.fmt_price(price))
    return text


async def _show_product(msg: Message, db: Database, product_id: int, edit: bool) -> None:
    p = await db.get_product(product_id)
    if not p or not p["active"]:
        await msg.answer(texts.NO_PRODUCTS)
        return
    text, markup = _card_text(p), kb.product(p["id"])
    await (msg.edit_text(text, reply_markup=markup) if edit
           else msg.answer(text, reply_markup=markup))


async def _discount_for(state: FSMContext, db: Database, product: dict,
                        user_id: int) -> tuple[dict | None, int]:
    """تخفیف ذخیره‌شده در FSM را دوباره اعتبارسنجی می‌کند (ممکن است بین مراحل منقضی شده باشد)."""
    data = await state.get_data()
    code = data.get("discount_code") if data.get("discount_product") == product["id"] else None
    if not code:
        return None, product["price"]
    d, _err = await discounts.check(db, code, product, user_id)
    if not d:
        await state.update_data(discount_code=None, discount_product=None)
        return None, product["price"]
    return d, discounts.price_after(d, product["price"])


async def _create_order(cb: CallbackQuery, state: FSMContext, db: Database,
                        settings: Settings, bot: Bot, product: dict,
                        method: str) -> tuple[int, int] | None:
    """(order_id, amount) یا None (با پیام خطا). تخفیف را اتمیک رزرو می‌کند."""
    d, amount = await _discount_for(state, db, product, cb.from_user.id)
    if method == "zarinpal" and 0 < amount < ONLINE_MIN_TOMAN:
        await cb.answer(texts.ONLINE_MIN, show_alert=True)
        return None
    code = d["code"] if d else None
    if code and not await db.reserve_discount(code):
        await state.update_data(discount_code=None, discount_product=None)
        await cb.answer(discounts.EXHAUSTED, show_alert=True)
        return None
    order_id = await db.create_order(cb.from_user.id, product, method, amount, code)
    await state.update_data(discount_code=None, discount_product=None)
    if amount == 0:  # تخفیف ۱۰۰٪
        await cb.message.edit_text(texts.FREE_ORDER.format(order_id=order_id))
        await complete_order(bot, db, settings, order_id)
        await cb.answer()
        return None
    return order_id, amount


# ---------- شروع / منو ----------
@router.message(CommandStart())
async def start(message: Message, command: CommandObject, db: Database,
                state: FSMContext) -> None:
    await state.clear()
    u = message.from_user
    payload = (command.args or "").strip()
    is_new = await db.upsert_user(u.id, u.username, u.full_name, payload or None)
    if is_new and payload.startswith("ref_") and payload[4:].isdigit():
        await db.add_referral(u.id, int(payload[4:]))
    if payload.startswith("p_") and payload[2:].isdigit():  # لینک مستقیم به دوره
        await _show_product(message, db, int(payload[2:]), edit=False)
        return
    await message.answer(texts.WELCOME.format(name=escape(u.first_name)),
                         reply_markup=kb.main_menu())


@router.message(Command("cancel"), StateFilter("*"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELED, reply_markup=kb.main_menu())


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer("برای شروع /start را بزن.", reply_markup=kb.main_menu())


@router.callback_query(F.data.in_({"menu", "fs:check"}))
async def menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
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


@router.callback_query(F.data.regexp(r"^p:\d+$"))
async def product(cb: CallbackQuery, db: Database) -> None:
    await _show_product(cb.message, db, int(cb.data.split(":")[1]), edit=True)
    await cb.answer()


# ---------- خرید ----------
@router.callback_query(F.data.regexp(r"^buy:\d+$"))
async def buy(cb: CallbackQuery, db: Database, settings: Settings, bot: Bot,
              state: FSMContext) -> None:
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
    d, price = await _discount_for(state, db, p, cb.from_user.id)
    await cb.message.edit_text(
        _card_text(p, price, d["code"] if d else None) + "\n\n" + texts.CHOOSE_METHOD,
        reply_markup=kb.methods(product_id, settings.zarinpal_enabled, settings.card_enabled))
    await cb.answer()


@router.callback_query(F.data.startswith("disc:"))
async def ask_discount(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DiscountState.code)
    await state.update_data(discount_ask=int(cb.data.split(":")[1]))
    await cb.message.answer(texts.ASK_DISCOUNT)
    await cb.answer()


@router.message(DiscountState.code, F.text)
async def got_discount(message: Message, db: Database, settings: Settings,
                       state: FSMContext) -> None:
    data = await state.get_data()
    p = await db.get_product(data.get("discount_ask", 0))
    if not p or not p["active"]:
        await state.clear()
        await message.answer(texts.NO_PRODUCTS, reply_markup=kb.main_menu())
        return
    d, err = await discounts.check(db, message.text, p, message.from_user.id)
    if not d:
        await message.answer(err + "\nدوباره بفرست یا /cancel بزن.")
        return
    await state.set_state(None)
    await state.update_data(discount_code=d["code"], discount_product=p["id"])
    price = discounts.price_after(d, p["price"])
    await message.answer(
        _card_text(p, price, d["code"]) + "\n\n" + texts.CHOOSE_METHOD,
        reply_markup=kb.methods(p["id"], settings.zarinpal_enabled, settings.card_enabled))


@router.callback_query(F.data.startswith("pay:z:"))
async def pay_online(cb: CallbackQuery, db: Database, settings: Settings, bot: Bot,
                     state: FSMContext, zarinpal: Zarinpal | None) -> None:
    if not (settings.zarinpal_enabled and zarinpal):
        await cb.answer(texts.NO_METHODS, show_alert=True)
        return
    p = await db.get_product(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        await cb.answer(texts.NO_PRODUCTS, show_alert=True)
        return
    created = await _create_order(cb, state, db, settings, bot, p, "zarinpal")
    if not created:
        return
    order_id, amount = created
    try:
        authority, url = await zarinpal.request(
            amount, f"{settings.public_base_url}/pay/callback",
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
async def pay_card(cb: CallbackQuery, db: Database, settings: Settings, bot: Bot,
                   state: FSMContext) -> None:
    if not settings.card_enabled:
        await cb.answer(texts.NO_METHODS, show_alert=True)
        return
    p = await db.get_product(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        await cb.answer(texts.NO_PRODUCTS, show_alert=True)
        return
    created = await _create_order(cb, state, db, settings, bot, p, "card")
    if not created:
        return
    order_id, amount = created
    holder = f"به نام {escape(settings.card_holder)}" if settings.card_holder else ""
    await cb.message.edit_text(texts.CARD_INFO.format(
        order_id=order_id, price=kb.fmt_price(amount),
        card=escape(settings.card_number), holder=holder))
    await cb.answer()


# ---------- پشتیبانی ----------
@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery, settings: Settings) -> None:
    text = (texts.SUPPORT.format(username=settings.support_username)
            if settings.support_username else texts.SUPPORT_NONE)
    await cb.message.edit_text(text, reply_markup=kb.support(bool(settings.support_username)))
    await cb.answer()


@router.callback_query(F.data == "support:msg")
async def support_ask(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SupportState.message)
    await cb.message.answer(texts.SUPPORT_ASK)
    await cb.answer()


@router.message(SupportState.message)
async def support_send(message: Message, bot: Bot, db: Database, settings: Settings,
                       state: FSMContext) -> None:
    await state.clear()
    header = (f"💬 پیام پشتیبانی از {escape(message.from_user.full_name)} "
              f"(<code>{message.from_user.id}</code>) — برای پاسخ، روی همین پیام Reply بزن")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, header)
            copied = await bot.copy_message(admin_id, message.chat.id, message.message_id)
            await db.add_support_msg(admin_id, copied.message_id, message.from_user.id)
        except Exception:
            log.exception("support relay to %s failed", admin_id)
    await message.answer(texts.SUPPORT_SENT, reply_markup=kb.main_menu())


# ---------- معرفی دوستان ----------
@router.callback_query(F.data == "ref")
async def referral(cb: CallbackQuery, db: Database, bot: Bot) -> None:
    username = (await bot.me()).username
    stats = await db.referral_stats(cb.from_user.id)
    await cb.message.edit_text(
        texts.REFERRAL_INFO.format(
            link=f"https://t.me/{username}?start=ref_{cb.from_user.id}", **stats),
        reply_markup=kb.main_menu(), disable_web_page_preview=True)
    await cb.answer()


# ---------- رسید کارت‌به‌کارت ----------
@router.message(F.photo, StateFilter(None))
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
               f"کاربر: {escape(message.from_user.full_name)} (<code>{message.from_user.id}</code>)")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_photo(admin_id, file_id, caption=caption,
                                 reply_markup=kb.receipt_review(order["id"]))
        except Exception:
            log.exception("cannot notify admin %s", admin_id)


# ---------- دوره‌های من ----------
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
