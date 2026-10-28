from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from aiogram.utils.keyboard import InlineKeyboardBuilder


def fmt_price(n: int) -> str:
    return f"{n:,}"


def main_menu() -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="📚 دوره‌ها", callback_data="catalog"))
    b.row(Btn(text="🎒 دوره‌های من", callback_data="mine"),
          Btn(text="🎁 دعوت دوستان", callback_data="ref"))
    b.row(Btn(text="💬 پشتیبانی", callback_data="support"))
    return b.as_markup()


def support(has_username: bool) -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="✉️ ارسال پیام به پشتیبانی", callback_data="support:msg"))
    b.row(Btn(text="⬅️ منو", callback_data="menu"))
    return b.as_markup()


def catalog(products: list[dict], labels: dict[int, str] | None = None) -> Kb:
    b = InlineKeyboardBuilder()
    for p in products:
        label = (labels or {}).get(p["id"]) or f"{p['title']} — {fmt_price(p['price'])} ت"
        b.row(Btn(text=label, callback_data=f"p:{p['id']}"))
    b.row(Btn(text="⬅️ منو", callback_data="menu"))
    return b.as_markup()


def product(product_id: int, available: bool = True) -> Kb:
    b = InlineKeyboardBuilder()
    if available:
        b.row(Btn(text="🛒 خرید و دریافت دسترسی", callback_data=f"buy:{product_id}"))
    else:
        b.row(Btn(text="💬 اطلاع از ظرفیت بعدی", callback_data="support"))
    b.row(Btn(text="⬅️ دوره‌ها", callback_data="catalog"))
    return b.as_markup()


def methods(product_id: int, zarinpal: bool, card: bool) -> Kb:
    b = InlineKeyboardBuilder()
    b.row(Btn(text="🏷 کد تخفیف دارم", callback_data=f"disc:{product_id}"))
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
          Btn(text="🛒 سفارش‌های اخیر", callback_data="adm:orders"))
    b.row(Btn(text="🏷 کدهای تخفیف", callback_data="adm:discounts"),
          Btn(text="📊 آمار", callback_data="adm:stats"))
    b.row(Btn(text="📣 پیام همگانی", callback_data="adm:bc"),
          Btn(text="📤 خروجی CSV", callback_data="adm:export"))
    return b.as_markup()


def admin_discounts(items: list[dict]) -> Kb:
    b = InlineKeyboardBuilder()
    for d in items:
        label = f"{d['value']}٪" if d["kind"] == "percent" else f"{fmt_price(d['value'])} ت"
        cap = "∞" if d["max_uses"] is None else d["max_uses"]
        b.row(Btn(text=f"🗑 {d['code']} ({label}) {d['used']}/{cap}",
                  callback_data=f"adm:ddel:{d['code']}"))
    b.row(Btn(text="➕ کد جدید", callback_data="adm:dnew"))
    b.row(Btn(text="⬅️ پنل", callback_data="adm:menu"))
    return b.as_markup()


def admin_orders(items: list[dict]) -> Kb:
    b = InlineKeyboardBuilder()
    for o in items:
        b.row(Btn(text=f"#{o['id']} {o['title']} — {o['status']}",
                  callback_data=f"adm:o:{o['id']}"))
    b.row(Btn(text="⬅️ پنل", callback_data="adm:menu"))
    return b.as_markup()


def admin_order(order: dict) -> Kb:
    b = InlineKeyboardBuilder()
    if order["status"] == "paid":
        b.row(Btn(text="↩️ استرداد و قطع دسترسی", callback_data=f"adm:refund:{order['id']}"))
        b.row(Btn(text="📨 ارسال دوباره دسترسی", callback_data=f"adm:resend:{order['id']}"))
    b.row(Btn(text="⬅️ سفارش‌ها", callback_data="adm:orders"))
    return b.as_markup()


def admin_product(p: dict) -> Kb:
    b = InlineKeyboardBuilder()
    state = "🔴 غیرفعال کن" if p["active"] else "🟢 فعال کن"
    b.row(Btn(text=state, callback_data=f"adm:tog:{p['id']}"),
          Btn(text="🗑 حذف", callback_data=f"adm:del:{p['id']}"))
    b.row(Btn(text="🔑 افزودن کد لایسنس", callback_data=f"adm:codes:{p['id']}"))
    b.row(Btn(text="✏️ عنوان", callback_data=f"adm:ed:title:{p['id']}"),
          Btn(text="✏️ توضیح", callback_data=f"adm:ed:description:{p['id']}"))
    b.row(Btn(text="✏️ قیمت", callback_data=f"adm:ed:price:{p['id']}"),
          Btn(text="✏️ کانال", callback_data=f"adm:ed:channel_id:{p['id']}"),
          Btn(text="✏️ متن دسترسی", callback_data=f"adm:ed:access_text:{p['id']}"))
    b.row(Btn(text="🖼 کاور", callback_data=f"adm:ed:cover_file_id:{p['id']}"),
          Btn(text="✅ مزایا", callback_data=f"adm:ed:features:{p['id']}"),
          Btn(text="🛡 ضمانت", callback_data=f"adm:ed:guarantee:{p['id']}"))
    b.row(Btn(text="👀 پیش‌نمایش", callback_data=f"adm:ed:preview_url:{p['id']}"),
          Btn(text="💺 ظرفیت", callback_data=f"adm:ed:seats:{p['id']}"))
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


def rating(order_id: int) -> Kb:
    return Kb(inline_keyboard=[[
        Btn(text="⭐" * n, callback_data=f"rate:{order_id}:{n}") for n in (1, 2, 3, 4, 5)]])
