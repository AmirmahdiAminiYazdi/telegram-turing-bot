"""متن کارت دوره. فقط داده‌ی واقعی نشان می‌دهد: فروش، امتیاز و ظرفیت از دیتابیس می‌آیند
و تا به حد معنادار نرسیده‌اند (۵ فروش، ۳ نظر) نمایش داده نمی‌شوند."""
from __future__ import annotations

from html import escape
from typing import Any

MIN_SOLD_SHOWN = 5
MIN_RATINGS_SHOWN = 3
CAPTION_LIMIT = 1000  # سقف تلگرام برای کپشن عکس ۱۰۲۴ است


def fmt_price(n: int) -> str:
    return f"{n:,}"


def time_left(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} روز و {hours} ساعت"
    if hours:
        return f"{hours} ساعت و {minutes} دقیقه"
    return f"{max(minutes, 1)} دقیقه"


def social_line(p: dict[str, Any]) -> str:
    parts = []
    if p.get("rating_count", 0) >= MIN_RATINGS_SHOWN:
        parts.append(f"⭐ {p['rating']} ({p['rating_count']} نظر)")
    if p.get("sold", 0) >= MIN_SOLD_SHOWN:
        parts.append(f"👥 {p['sold']} نفر خریده‌اند")
    return " · ".join(parts)


def price_block(p: dict[str, Any], final_price: int | None = None) -> str:
    price = p["price"] if final_price is None else final_price
    lines = []
    if p.get("on_sale"):
        lines.append(f"💰 <s>{fmt_price(p['list_price'])}</s> ← <b>{fmt_price(price)}</b> تومان")
        lines.append(f"⏳ قیمت ویژه تا {time_left(p['sale_left'])} دیگر")
    elif final_price is not None and final_price != p["price"]:
        lines.append(f"💰 <s>{fmt_price(p['price'])}</s> ← <b>{fmt_price(price)}</b> تومان")
    else:
        lines.append(f"💰 <b>{fmt_price(price)}</b> تومان")
    return "\n".join(lines)


def availability(p: dict[str, Any]) -> str:
    left = p.get("seats_left")
    if left is None:
        return ""
    if left <= 0:
        return "⛔ ظرفیت این دوره تکمیل شده است"
    return f"🔥 {left} جای خالی از {p['seats']}"


def sold_out(p: dict[str, Any]) -> bool:
    return p.get("seats_left") == 0


def product_card(p: dict[str, Any], final_price: int | None = None,
                 limit: int | None = None) -> str:
    head = [f"🎓 <b>{escape(p['title'])}</b>"]
    social = social_line(p)
    if social:
        head.append(social)

    tail: list[str] = []
    if p.get("features"):
        items = [f"✅ {escape(x.strip())}" for x in p["features"].splitlines() if x.strip()]
        tail.append("\n".join(items[:8]))
    if p.get("guarantee"):
        tail.append(f"🛡 {escape(p['guarantee'])}")
    if p.get("preview_url"):
        tail.append(f"👀 پیش‌نمایش: {escape(p['preview_url'])}")
    tail.append(price_block(p, final_price))
    avail = availability(p)
    if avail:
        tail.append(avail)

    head_text = "\n".join(head)
    tail_text = "\n\n".join(tail)
    desc = escape(p["description"]).strip()
    if limit:
        room = limit - len(head_text) - len(tail_text) - 8
        if len(desc) > room:
            desc = desc[: max(room - 1, 0)].rstrip() + "…"
    body = [head_text] + ([desc] if desc else []) + [tail_text]
    return "\n\n".join(body)


def catalog_label(p: dict[str, Any], bestseller_id: int | None) -> str:
    badge = "🔥 " if p["id"] == bestseller_id else ("🏷 " if p.get("on_sale") else "")
    suffix = " ⛔" if sold_out(p) else ""
    return f"{badge}{p['title']} · {fmt_price(p['price'])} ت{suffix}"
