"""وارد کردن دسته‌ای دوره‌ها از فایل JSON.

    python -m bot.tools.import_products courses.json [--update]

هر دوره یک شیء است. فیلدهای اجباری: title, price (تومان). بقیه اختیاری:
description, features (فهرست یا متن چندخطی), guarantee, preview_url, channel_id,
access_text, seats. دوره‌ی هم‌نام (title) با --update به‌روز می‌شود، وگرنه رد می‌شود.
امتیاز، فروش و حراج وارد نمی‌شوند؛ این‌ها از داده‌ی واقعی ربات می‌آیند.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from bot.db import Database

OPTIONAL = ("description", "guarantee", "preview_url", "channel_id", "access_text", "seats")


class ImportError_(ValueError):
    pass


def normalize(item: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(item.get("title", "")).strip()
    price = item.get("price")
    if not title:
        raise ImportError_(f"#{index}: title خالی است")
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
        raise ImportError_(f"#{index} «{title}»: price باید عدد صحیح مثبت (تومان) باشد")
    features = item.get("features")
    if isinstance(features, list):
        features = "\n".join(str(f).strip() for f in features if str(f).strip())
    out: dict[str, Any] = {"title": title, "price": price,
                           "features": (features or "").strip() or None}
    for key in OPTIONAL:
        value = item.get(key)
        out[key] = value if value not in ("", None) else None
    if out["description"] is None:
        out["description"] = ""
    for key in ("channel_id", "seats"):
        if out[key] is not None and not isinstance(out[key], int):
            raise ImportError_(f"#{index} «{title}»: {key} باید عدد باشد")
    return out


async def import_products(db: Database, items: list[dict[str, Any]],
                          update: bool = False) -> dict[str, int]:
    rows = [normalize(it, i + 1) for i, it in enumerate(items)]  # اول همه اعتبارسنجی شوند
    result = {"created": 0, "updated": 0, "skipped": 0}
    existing = {p["title"]: p for p in await db.list_products(only_active=False)}
    for r in rows:
        found = existing.get(r["title"])
        if found and not update:
            result["skipped"] += 1
            continue
        if found:
            for field in ("description", "price", "channel_id", "access_text", "features",
                          "guarantee", "preview_url", "seats"):
                await db.update_product(found["id"], field, r[field])
            result["updated"] += 1
            continue
        pid = await db.add_product(r["title"], r["description"], r["price"],
                                   r["channel_id"], r["access_text"])
        for field in ("features", "guarantee", "preview_url", "seats"):
            if r[field] is not None:
                await db.update_product(pid, field, r[field])
        result["created"] += 1
    return result


async def _main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    with open(args.file, encoding="utf-8") as f:
        items = json.load(f)
    db = Database(os.environ.get("DB_PATH", "data/bot.sqlite3"))
    await db.connect()
    try:
        print(await import_products(db, items, args.update))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(_main())
