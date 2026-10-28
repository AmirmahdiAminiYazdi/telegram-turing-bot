from __future__ import annotations

import logging

from aiogram import Bot
from aiohttp import web

from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.services.delivery import deliver
from bot.services.zarinpal import Zarinpal, ZarinpalError

log = logging.getLogger(__name__)

PAGE = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>پرداخت</title>
<style>body{{font-family:Tahoma,sans-serif;text-align:center;padding:12vh 16px}}
a{{display:inline-block;margin-top:24px;padding:12px 24px;background:#2a9df4;color:#fff;
border-radius:8px;text-decoration:none}}</style></head><body>
<h2>{title}</h2><p>{body}</p>{button}</body></html>"""


def _page(ok: bool, bot_username: str) -> web.Response:
    button = f'<a href="https://t.me/{bot_username}">بازگشت به ربات</a>' if bot_username else ""
    return web.Response(
        text=PAGE.format(
            title="✅ پرداخت موفق" if ok else "❌ پرداخت ناموفق",
            body="دوره‌ات به‌زودی در ربات تحویل داده می‌شود." if ok else texts.PAID_FAILED,
            button=button),
        content_type="text/html")


async def callback(request: web.Request) -> web.Response:
    app = request.app
    db: Database = app["db"]
    bot: Bot = app["bot"]
    zarinpal: Zarinpal = app["zarinpal"]
    settings: Settings = app["settings"]
    username = app.get("bot_username", "")

    authority = request.query.get("Authority", "")
    order = await db.get_order_by_authority(authority) if authority else None
    if not order or order["method"] != "zarinpal":
        return _page(False, username)

    if order["status"] == "paid":  # رفرش صفحه / تماس تکراری
        return _page(True, username)

    if request.query.get("Status") != "OK":
        return _page(False, username)

    try:
        ref_id = await zarinpal.verify(order["amount"], authority)
    except ZarinpalError:
        log.exception("verify failed for order %s", order["id"])
        return _page(False, username)
    if ref_id is None:
        return _page(False, username)

    if await db.mark_paid(order["id"], ref_id):  # فقط یک‌بار تحویل
        try:
            await bot.send_message(order["user_id"], texts.PAID_OK)
            await deliver(bot, db, order, settings.admin_ids)
        except Exception:
            log.exception("delivery failed for order %s", order["id"])
    return _page(True, username)


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def make_app(db: Database, bot: Bot, settings: Settings,
             zarinpal: Zarinpal | None) -> web.Application:
    app = web.Application()
    app["db"], app["bot"], app["settings"], app["zarinpal"] = db, bot, settings, zarinpal
    app.router.add_get("/pay/callback", callback)
    app.router.add_get("/health", health)
    return app
