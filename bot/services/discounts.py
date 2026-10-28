from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bot.db import Database

# پیام‌های خطا برای کاربر
NOT_FOUND = "کد تخفیف معتبر نیست."
EXPIRED = "این کد تخفیف منقضی شده است."
EXHAUSTED = "ظرفیت این کد تخفیف تمام شده است."
WRONG_PRODUCT = "این کد برای این دوره قابل استفاده نیست."
NOT_YOURS = "این کد برای حساب دیگری صادر شده است."


def price_after(discount: dict[str, Any], price: int) -> int:
    if discount["kind"] == "percent":
        return max(price - price * discount["value"] // 100, 0)
    return max(price - discount["value"], 0)


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")  # هم‌فرمت datetime('now') در SQLite
    return expires_at <= now


async def check(db: Database, code: str, product: dict[str, Any],
                user_id: int) -> tuple[dict[str, Any] | None, str | None]:
    """(تخفیف, None) یا (None, پیام خطا). رزرو نمی‌کند؛ رزرو هنگام ساخت سفارش است."""
    d = await db.get_discount(code.strip())
    if not d:
        return None, NOT_FOUND
    if d["owner_id"] and d["owner_id"] != user_id:
        return None, NOT_YOURS
    if d["product_id"] and d["product_id"] != product["id"]:
        return None, WRONG_PRODUCT
    if _expired(d["expires_at"]):
        return None, EXPIRED
    if d["max_uses"] is not None and d["used"] >= d["max_uses"]:
        return None, EXHAUSTED
    return d, None
