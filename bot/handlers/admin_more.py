from __future__ import annotations

import csv
import io
import logging
import secrets
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.filters import IsAdmin
from bot.services.delivery import deliver
from bot.services.fulfillment import REFERRAL_DEFAULT_PERCENT

log = logging.getLogger(__name__)
router = Router(name="admin_more")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

SETTING_KEYS = {"force_channel", "force_channel_link", "referral_percent", "loyalty_percent"}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_int(raw: str) -> int | None:
    s = raw.translate(_DIGITS).replace(",", "").replace("،", "").strip()
    return int(s) if s.isdigit() else None


class NewDiscount(StatesGroup):
    code = State()
    value = State()
    uses = State()
    days = State()


class EditProduct(StatesGroup):
    value = State()


# ---------- کدهای تخفیف ----------
@router.callback_query(F.data == "adm:discounts")
async def discounts_list(cb: CallbackQuery, db: Database) -> None:
    items = await db.list_discounts()
    await cb.message.edit_text(
        "کدهای تخفیف (برای حذف روی کد بزن):" if items else "کدی ثبت نشده است.",
        reply_markup=kb.admin_discounts(items))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ddel:"))
async def discount_delete(cb: CallbackQuery, db: Database) -> None:
    await db.delete_discount(cb.data.split(":", 2)[2])
    await discounts_list(cb, db)


@router.callback_query(F.data == "adm:dnew")
async def discount_new(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewDiscount.code)
    await cb.message.answer("نام کد (انگلیسی/عدد)؟ برای ساخت خودکار <code>-</code> بفرست. (/cancel)")
    await cb.answer()


@router.message(NewDiscount.code, F.text)
async def discount_code(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    code = f"OFF-{secrets.token_hex(3).upper()}" if raw == "-" else raw.upper()
    if not code.replace("-", "").replace("_", "").isalnum() or not code.isascii():
        await message.answer("فقط حروف انگلیسی، عدد، - و _ مجاز است.")
        return
    await state.update_data(code=code)
    await state.set_state(NewDiscount.value)
    await message.answer("مقدار تخفیف؟ درصدی: <code>20%</code> — مبلغ ثابت به تومان: <code>50000</code>")


@router.message(NewDiscount.value, F.text)
async def discount_value(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    percent = raw.endswith("%") or raw.endswith("٪")
    n = to_int(raw.rstrip("%٪"))
    if n is None or n <= 0 or (percent and n > 100):
        await message.answer("مقدار معتبر نیست (درصد ۱ تا ۱۰۰ یا مبلغ مثبت).")
        return
    await state.update_data(kind="percent" if percent else "fixed", value=n)
    await state.set_state(NewDiscount.uses)
    await message.answer("حداکثر دفعات استفاده؟ (عدد یا <code>-</code> برای نامحدود)")


@router.message(NewDiscount.uses, F.text)
async def discount_uses(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    uses = None if raw == "-" else to_int(raw)
    if raw != "-" and (uses is None or uses <= 0):
        await message.answer("عدد مثبت یا - بفرست.")
        return
    await state.update_data(max_uses=uses)
    await state.set_state(NewDiscount.days)
    await message.answer("چند روز اعتبار داشته باشد؟ (عدد یا <code>-</code> برای بدون انقضا)")


@router.message(NewDiscount.days, F.text)
async def discount_days(message: Message, state: FSMContext, db: Database) -> None:
    raw = message.text.strip()
    days = None if raw == "-" else to_int(raw)
    if raw != "-" and (days is None or days <= 0):
        await message.answer("عدد مثبت یا - بفرست.")
        return
    d = await state.get_data()
    await state.clear()
    ok = await db.create_discount(d["code"], d["kind"], d["value"], d["max_uses"], days)
    await message.answer(
        f"✅ کد <code>{d['code']}</code> ساخته شد." if ok else "این کد قبلاً وجود دارد.",
        reply_markup=kb.admin_menu())


# ---------- ویرایش محصول ----------
@router.callback_query(F.data.startswith("adm:ed:"))
async def edit_start(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, field, pid = cb.data.split(":")
    await state.set_state(EditProduct.value)
    await state.update_data(field=field, product_id=int(pid))
    hint = {
        "price": "قیمت جدید (تومان)", "channel_id": "آیدی عددی کانال (یا - برای حذف)",
        "access_text": "متن دسترسی (یا - برای حذف)",
        "cover_file_id": "یک عکس بفرست تا کاور دوره شود (یا - برای حذف)",
        "features": "مزایا را بفرست، هر مزیت در یک خط، حداکثر ۸ خط (یا - برای حذف)",
        "guarantee": "متن ضمانت، مثلاً «ضمانت بازگشت وجه ۷ روزه» (یا - برای حذف). "
                     "فقط چیزی بنویس که واقعاً به آن عمل می‌کنی",
        "preview_url": "لینک پیش‌نمایش/نمونه جلسه (یا - برای حذف)",
        "seats": "ظرفیت کل دوره (عدد) یا - برای نامحدود. فقط اگر محدودیت واقعی دارد",
    }.get(field, "مقدار جدید")
    await cb.message.answer(f"{hint}؟ (/cancel)")
    await cb.answer()


@router.message(EditProduct.value, F.text)
async def edit_save(message: Message, state: FSMContext, db: Database) -> None:
    d = await state.get_data()
    field, raw = d["field"], message.text.strip()
    value: int | str | None = raw
    if field == "price":
        value = to_int(raw)
        if not value:
            await message.answer("قیمت معتبر نیست.")
            return
    elif field == "channel_id":
        value = None
        if raw != "-":
            try:
                value = int(raw)
            except ValueError:
                await message.answer("آیدی عددی نیست.")
                return
    elif field == "seats":
        value = None if raw == "-" else to_int(raw)
        if raw != "-" and not value:
            await message.answer("عدد مثبت یا - بفرست.")
            return
    elif field == "cover_file_id":
        if raw != "-":
            await message.answer("عکس بفرست یا - برای حذف.")
            return
        value = None
    elif raw == "-":
        value = None
    await db.update_product(d["product_id"], field, value)
    await state.clear()
    await message.answer("✅ ذخیره شد.", reply_markup=kb.admin_menu())


@router.message(EditProduct.value, F.photo)
async def edit_cover(message: Message, state: FSMContext, db: Database) -> None:
    d = await state.get_data()
    if d["field"] != "cover_file_id":
        await message.answer("برای این فیلد متن بفرست.")
        return
    await db.update_product(d["product_id"], "cover_file_id", message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ کاور ذخیره شد.", reply_markup=kb.admin_menu())


@router.message(Command("sale"))
async def sale_cmd(message: Message, db: Database) -> None:
    """/sale <id> <قیمت> <ساعت>  یا  /sale <id> off  (پایان خودکار؛ بعد از مهلت قیمت اصلی برمی‌گردد)"""
    parts = (message.text or "").split()[1:]
    usage = "استفاده:\n<code>/sale 3 450000 48</code> (قیمت ویژه ۴۸ ساعته)\n<code>/sale 3 off</code>"
    pid = to_int(parts[0]) if parts else None
    product = await db.get_product(pid) if pid else None
    if not product or len(parts) < 2:
        await message.answer(usage)
        return
    if parts[1] == "off":
        await db.set_sale(product["id"], None, None)
        await message.answer("حراج پایان یافت.")
        return
    price, hours = to_int(parts[1]), to_int(parts[2]) if len(parts) > 2 else None
    if not price or not hours or price >= product["list_price"]:
        await message.answer("قیمت ویژه باید کمتر از قیمت اصلی باشد و مدت (ساعت) را هم بده.\n" + usage)
        return
    await db.set_sale(product["id"], price, hours)
    await message.answer(f"✅ قیمت ویژه {price:,} تومان تا {hours} ساعت دیگر فعال شد.")


# ---------- سفارش‌ها ----------
@router.callback_query(F.data == "adm:orders")
async def orders_list(cb: CallbackQuery, db: Database) -> None:
    items = await db.recent_orders()
    await cb.message.edit_text("سفارش‌های اخیر:" if items else "سفارشی نیست.",
                               reply_markup=kb.admin_orders(items))
    await cb.answer()


async def _order_text(db: Database, order_id: int) -> tuple[str, dict] | None:
    o = await db.order_details(order_id)
    if not o:
        return None
    user = escape(o["full_name"] or "—") + (f" @{o['username']}" if o["username"] else "")
    lines = [f"سفارش #{o['id']} — {escape(o['title'])}", f"کاربر: {user} (<code>{o['user_id']}</code>)",
             f"مبلغ: {kb.fmt_price(o['amount'])} تومان", f"روش: {o['method']} | وضعیت: {o['status']}"]
    if o["discount_code"]:
        lines.append(f"کد تخفیف: {escape(o['discount_code'])}")
    if o["ref_id"]:
        lines.append(f"کد پیگیری درگاه: {escape(o['ref_id'])}")
    return "\n".join(lines), o


@router.callback_query(F.data.regexp(r"^adm:o:\d+$"))
async def order_view(cb: CallbackQuery, db: Database) -> None:
    res = await _order_text(db, int(cb.data.split(":")[2]))
    if not res:
        await cb.answer("پیدا نشد", show_alert=True)
        return
    await cb.message.edit_text(res[0], reply_markup=kb.admin_order(res[1]))
    await cb.answer()


@router.message(Command("order"))
async def order_cmd(message: Message, db: Database) -> None:
    arg = (message.text or "").split(maxsplit=1)[1:]
    res = await _order_text(db, to_int(arg[0]) or 0) if arg else None
    if not res:
        await message.answer("استفاده: <code>/order 123</code>")
        return
    await message.answer(res[0], reply_markup=kb.admin_order(res[1]))


@router.callback_query(F.data.startswith("adm:resend:"))
async def order_resend(cb: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    o = await db.get_order(int(cb.data.split(":")[2]))
    if o and o["status"] == "paid":
        await deliver(bot, db, o, settings.admin_ids)
        await cb.answer("ارسال شد")
    else:
        await cb.answer("سفارش پرداخت‌شده نیست", show_alert=True)


@router.callback_query(F.data.startswith("adm:refund:"))
async def order_refund(cb: CallbackQuery, db: Database, bot: Bot) -> None:
    o = await db.order_details(int(cb.data.split(":")[2]))
    if not o or not await db.refund_order(o["id"]):
        await cb.answer("قابل استرداد نیست", show_alert=True)
        return
    kicked = ""
    if o["channel_id"]:
        try:  # ban + unban یعنی حذف از کانال بدون مسدود ماندن
            await bot.ban_chat_member(o["channel_id"], o["user_id"])
            await bot.unban_chat_member(o["channel_id"], o["user_id"], only_if_banned=True)
            kicked = " و از کانال حذف شد"
        except Exception:
            log.exception("kick failed")
            kicked = " (حذف از کانال ناموفق؛ دستی انجام بده)"
    try:
        await bot.send_message(o["user_id"], f"سفارش #{o['id']} استرداد شد و دسترسی‌ات قطع شد.")
    except Exception:
        pass
    await cb.message.edit_text(
        f"↩️ سفارش #{o['id']} استرداد شد{kicked}.\nمبلغ را خودت به مشتری برگردان؛ ربات پول جابه‌جا نمی‌کند.",
        reply_markup=kb.admin_menu())
    await cb.answer()


@router.callback_query(F.data == "adm:export")
async def export_csv(cb: CallbackQuery, db: Database) -> None:
    rows = await db.all_orders()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "user_id", "course", "amount", "original", "discount", "method",
                "status", "ref_id", "created_at", "paid_at", "source"])
    for r in rows:
        w.writerow([r[k] for k in ("id", "user_id", "title", "amount", "original_amount",
                                   "discount_code", "method", "status", "ref_id",
                                   "created_at", "paid_at", "source")])
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM تا اکسل فارسی را درست بخواند
    await cb.message.answer_document(BufferedInputFile(data, "orders.csv"))
    await cb.answer()


# ---------- تنظیمات و پاسخ پشتیبانی ----------
@router.message(Command("set"))
async def set_cmd(message: Message, db: Database) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or parts[1] not in SETTING_KEYS:
        current = {k: await db.get_setting(k, "") for k in sorted(SETTING_KEYS)}
        await message.answer(
            "استفاده: <code>/set کلید مقدار</code> (برای پاک کردن: <code>-</code>)\n\n"
            + "\n".join(f"• <code>{k}</code> = {escape(v or '—')}" for k, v in current.items())
            + f"\n\nپیش‌فرض referral_percent = {REFERRAL_DEFAULT_PERCENT}")
        return
    key, value = parts[1], parts[2].strip()
    if value == "-":
        value = ""
    if key in {"referral_percent", "loyalty_percent"} and value and not (value.isdigit() and 0 <= int(value) <= 100):
        await message.answer("عدد ۰ تا ۱۰۰ بفرست.")
        return
    await db.set_setting(key, value)
    await message.answer("✅ ذخیره شد.")


@router.message(F.reply_to_message, StateFilter(None))
async def support_reply(message: Message, db: Database, bot: Bot) -> None:
    """ادمین روی پیام ارسال‌شده‌ی پشتیبانی Reply می‌زند؛ پاسخ به کاربر می‌رسد."""
    user_id = await db.support_user(message.chat.id, message.reply_to_message.message_id)
    if not user_id:
        return
    try:
        if message.text:
            await bot.send_message(user_id, texts.SUPPORT_REPLY.format(text=escape(message.text)))
        else:
            await bot.copy_message(user_id, message.chat.id, message.message_id)
        await message.answer("✅ ارسال شد.")
    except Exception:
        await message.answer("ارسال نشد (کاربر ربات را بلاک کرده؟).")
