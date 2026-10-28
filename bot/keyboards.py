from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from aiogram.utils.keyboard import InlineKeyboardBuilder


def fmt_price(n: int) -> str:
    return f"{n:,}"


def main_menu() -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="📚 دوره‌ها", callback_data="catalog"))
    b.row(Btn(text="🎒 دوره‌های من", callback_data="mine"),
          Btn(text="💬 پشتیبانی", callback_data="support"))
    return b.as_markup()


def catalog(products: list[dict]) -> Kb:
    b = InlineKeyboardBuilder()
    for p in products:
        b.row(Btn(text=f"{p['title']} — {fmt_price(p['price'])} ت",
                  callback_data=f"p:{p['id']}"))
    b.row(Btn(text="⬅️ منو", callback_data="menu"))
    return b.as_markup()


def product(product_id: int) -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="🛒 خرید", callback_data=f"buy:{product_id}"))
    b.row(Btn(text="⬅️ دوره‌ها", callback_data="catalog"))
    return b.as_markup()


def methods(product_id: int, zarinpal: bool, card: bool) -> Kb:
    b = InlineKeyboardBuilder()
    if zarinpal:
        b.row(Btn(text="💳 پرداخت آنلاین", callback_data=f"pay:z:{product_id}"))
    if card:
        b.row(Btn(text="🏦 کارت‌به‌کارت", callback_data=f"pay:c:{product_id}"))
    b.row(Btn(text="⬅️ برگشت", callback_data=f"p:{product_id}"))
    return b.as_markup()


def pay_link(url: str) -> Kb:
    return Kb(inline_keyboard=[[Btn(text="💳 رفتن به درگاه", url=url)]])


def mine(orders: list[dict]) -> Kb:
    b = InlineKeyboardBuilder()
    for o in orders:
        b.row(Btn(text=f"🔑 {o['title']}", callback_data=f"again:{o['id']}"))
    b.row(Btn(text="⬅️ منو", callback_data="menu"))
    return b.as_markup()


def receipt_review(order_id: int) -> Kb:
    return Kb(inline_keyboard=[[
        Btn(text="✅ تایید", callback_data=f"adm:ok:{order_id}"),
        Btn(text="❌ رد", callback_data=f"adm:no:{order_id}"),
    ]])


def admin_menu() -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="📦 محصولات", callback_data="adm:products"),
          Btn(text="➕ محصول جدید", callback_data="adm:new"))
    b.row(Btn(text="🧾 رسیدهای منتظر", callback_data="adm:pending"),
          Btn(text="📊 آمار", callback_data="adm:stats"))
    b.row(Btn(text="📣 ارسال پیام همگانی", callback_data="adm:bc"))
    return b.as_markup()


def admin_product(p: dict) -> Kb:
    b = InlineKeyboardBuilder()
    state = "🔴 غیرفعال کن" if p["active"] else "🟢 فعال کن"
    b.row(Btn(text=state, callback_data=f"adm:tog:{p['id']}"),
          Btn(text="🗑 حذف", callback_data=f"adm:del:{p['id']}"))
    b.row(Btn(text="🔑 افزودن کد لایسنس", callback_data=f"adm:codes:{p['id']}"))
    b.row(Btn(text="⬅️ برگشت", callback_data="adm:products"))
    return b.as_markup()


def admin_products(products: list[dict]) -> Kb:
    b = InlineKeyboardBuilder()
    for p in products:
        icon = "🟢" if p["active"] else "🔴"
        b.row(Btn(text=f"{icon} {p['title']} ({fmt_price(p['price'])})",
                  callback_data=f"adm:p:{p['id']}"))
    b.row(Btn(text="⬅️ پنل", callback_data="adm:menu"))
    return b.as_markup()
