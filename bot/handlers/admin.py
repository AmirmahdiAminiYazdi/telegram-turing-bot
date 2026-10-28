from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.services.delivery import deliver

log = logging.getLogger(__name__)
router = Router(name="admin")


class IsAdmin:
    """فیلتر ساده: فقط ادمین‌های تعریف‌شده در ADMIN_IDS."""

    def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user.id in settings.admin_ids


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class NewProduct(StatesGroup):
    title = State()
    description = State()
    price = State()
    channel = State()
    access = State()


class AddCodes(StatesGroup):
    codes = State()


class Broadcast(StatesGroup):
    text = State()


@router.message(Command("admin"))
async def admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("پنل ادمین", reply_markup=kb.admin_menu())


@router.message(Command("cancel"), StateFilter("*"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELED, reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm:menu")
async def menu(cb: CallbackQuery) -> None:
    await cb.message.edit_text("پنل ادمین", reply_markup=kb.admin_menu())
    await cb.answer()


# ---- محصولات ----
@router.callback_query(F.data == "adm:products")
async def products(cb: CallbackQuery, db: Database) -> None:
    items = await db.list_products(only_active=False)
    text = "محصولات:" if items else "محصولی ثبت نشده است."
    await cb.message.edit_text(text, reply_markup=kb.admin_products(items))
    await cb.answer()


async def _show_product(cb: CallbackQuery, db: Database, pid: int) -> None:
    p = await db.get_product(pid)
    if not p:
        await cb.answer("پیدا نشد", show_alert=True)
        return
    free = await db.free_codes_count(pid)
    text = (f"<b>{escape(p['title'])}</b>\nقیمت: {kb.fmt_price(p['price'])} تومان\n"
            f"کانال: {p['channel_id'] or '—'}\nکد آزاد: {free}\n"
            f"وضعیت: {'فعال' if p['active'] else 'غیرفعال'}")
    await cb.message.edit_text(text, reply_markup=kb.admin_product(p))
    await cb.answer()


@router.callback_query(F.data.regexp(r"^adm:p:\d+$"))
async def product(cb: CallbackQuery, db: Database) -> None:
    await _show_product(cb, db, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("adm:tog:"))
async def toggle(cb: CallbackQuery, db: Database) -> None:
    pid = int(cb.data.split(":")[2])
    await db.toggle_product(pid)
    await _show_product(cb, db, pid)


@router.callback_query(F.data.startswith("adm:del:"))
async def delete(cb: CallbackQuery, db: Database) -> None:
    ok = await db.delete_product(int(cb.data.split(":")[2]))
    if not ok:
        await cb.answer("این محصول سفارش دارد؛ به‌جای حذف، غیرفعالش کن.", show_alert=True)
        return
    items = await db.list_products(only_active=False)
    await cb.message.edit_text("حذف شد.", reply_markup=kb.admin_products(items))
    await cb.answer()


# ---- محصول جدید ----
@router.callback_query(F.data == "adm:new")
async def new_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewProduct.title)
    await cb.message.answer("عنوان دوره؟ (/cancel برای انصراف)")
    await cb.answer()


@router.message(NewProduct.title, F.text)
async def new_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(NewProduct.description)
    await message.answer("توضیحات دوره؟")


@router.message(NewProduct.description, F.text)
async def new_desc(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(NewProduct.price)
    await message.answer("قیمت به تومان؟ (فقط عدد)")


@router.message(NewProduct.price, F.text)
async def new_price(message: Message, state: FSMContext) -> None:
    raw = message.text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    raw = raw.replace(",", "").replace("،", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("عدد معتبر نیست؛ دوباره بفرست.")
        return
    await state.update_data(price=int(raw))
    await state.set_state(NewProduct.channel)
    await message.answer(
        "آیدی عددی کانال/گروه خصوصی دوره (مثل <code>-1001234567890</code>)؟\n"
        "ربات باید ادمین آن باشد. اگر ندارد، <code>-</code> بفرست.")


@router.message(NewProduct.channel, F.text)
async def new_channel(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    channel = None
    if raw != "-":
        try:
            channel = int(raw)
        except ValueError:
            await message.answer("آیدی عددی نیست؛ دوباره بفرست یا - بزن.")
            return
    await state.update_data(channel_id=channel)
    await state.set_state(NewProduct.access)
    await message.answer("متن/لینک دسترسی ثابت که بعد از خرید فرستاده شود؟ (یا -)")


@router.message(NewProduct.access, F.text)
async def new_access(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    access = None if message.text.strip() == "-" else message.text.strip()
    pid = await db.add_product(data["title"], data["description"], data["price"],
                               data["channel_id"], access)
    await state.clear()
    await message.answer(f"✅ دوره #{pid} ساخته شد.", reply_markup=kb.admin_menu())


# ---- کدهای لایسنس ----
@router.callback_query(F.data.startswith("adm:codes:"))
async def codes_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCodes.codes)
    await state.update_data(product_id=int(cb.data.split(":")[2]))
    await cb.message.answer("کدها را بفرست، هر کد در یک خط. (/cancel برای انصراف)")
    await cb.answer()


@router.message(AddCodes.codes, F.text)
async def codes_save(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    codes = [c.strip() for c in message.text.splitlines() if c.strip()]
    n = await db.add_codes(data["product_id"], codes)
    await state.clear()
    await message.answer(f"✅ {n} کد اضافه شد.", reply_markup=kb.admin_menu())


# ---- رسیدها ----
@router.callback_query(F.data == "adm:pending")
async def pending(cb: CallbackQuery, db: Database) -> None:
    items = await db.pending_receipts()
    if not items:
        await cb.answer("رسید منتظری نیست", show_alert=True)
        return
    for o in items:
        await cb.message.answer_photo(
            o["receipt_file_id"],
            caption=f"سفارش #{o['id']} — {escape(o['title'])} — "
                    f"{kb.fmt_price(o['amount'])} تومان",
            reply_markup=kb.receipt_review(o["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ok:"))
async def approve(cb: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    order = await db.get_order(int(cb.data.split(":")[2]))
    if not order or not await db.mark_paid(order["id"]):
        await cb.answer("قبلا بررسی شده است", show_alert=True)
        return
    await bot.send_message(order["user_id"], texts.PAID_OK)
    await deliver(bot, db, order, settings.admin_ids)
    await cb.message.edit_caption(caption=(cb.message.caption or "") + "\n\n✅ تایید شد")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:no:"))
async def reject(cb: CallbackQuery, db: Database, bot: Bot) -> None:
    order = await db.get_order(int(cb.data.split(":")[2]))
    if not order or not await db.reject_order(order["id"]):
        await cb.answer("قبلا بررسی شده است", show_alert=True)
        return
    await bot.send_message(order["user_id"], texts.REJECTED.format(order_id=order["id"]))
    await cb.message.edit_caption(caption=(cb.message.caption or "") + "\n\n❌ رد شد")
    await cb.answer()


# ---- آمار ----
@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery, db: Database) -> None:
    s = await db.stats()
    rate = f"{s['paid'] / s['orders'] * 100:.0f}%" if s["orders"] else "—"
    await cb.message.edit_text(
        f"👥 کاربران: {s['users']}\n🛒 سفارش‌ها: {s['orders']}\n"
        f"✅ پرداخت‌شده: {s['paid']} (نرخ تبدیل {rate})\n"
        f"💰 درآمد: {kb.fmt_price(s['revenue'])} تومان",
        reply_markup=kb.admin_menu())
    await cb.answer()


# ---- پیام همگانی ----
@router.callback_query(F.data == "adm:bc")
async def bc_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await cb.message.answer("متن پیام همگانی را بفرست. (/cancel برای انصراف)")
    await cb.answer()


@router.message(Broadcast.text, F.text)
async def bc_send(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    ok = fail = 0
    for uid in await db.user_ids():
        try:
            await bot.send_message(uid, message.text)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(uid, message.text)
                ok += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # زیر سقف ~۳۰ پیام در ثانیه تلگرام
    await message.answer(f"ارسال شد: {ok} | ناموفق: {fail}", reply_markup=kb.admin_menu())
