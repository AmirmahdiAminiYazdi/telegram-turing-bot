from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiohttp import web

from bot.app import create_dispatcher
from bot.config import load_settings, parse_ids
from bot.db import Database
from bot.handlers.setup import ClaimGate
from bot.services.reminders import reminder_loop
from bot.services.zarinpal import Zarinpal
from bot.web import make_app

log = logging.getLogger("bot")


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    db = Database(settings.db_path)
    await db.connect()
    settings.admin_ids.update(parse_ids(await db.get_setting("extra_admins")))

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.me()  # توکن غلط همین‌جا با پیام روشن می‌ایستد
    except Exception as exc:
        await bot.session.close()
        await db.close()
        raise SystemExit(f"اتصال به تلگرام ناموفق بود (توکن یا شبکه را بررسی کن): {exc}") from exc
    log.info("bot @%s started; admins=%d zarinpal=%s card=%s", me.username,
             len(settings.admin_ids), settings.zarinpal_enabled, settings.card_enabled)

    claim_gate = None
    if not settings.admin_ids:
        claim_gate = ClaimGate()
        log.warning("ادمینی تعریف نشده. در تلگرام به @%s بفرست: /claim %s",
                    me.username, claim_gate.code)

    zarinpal = (Zarinpal(settings.zarinpal_merchant_id, settings.zarinpal_sandbox)
                if settings.zarinpal_enabled else None)
    dp = create_dispatcher(db, settings, zarinpal, claim_gate)

    await bot.set_my_commands([
        BotCommand(command="start", description="شروع و منوی اصلی"),
        BotCommand(command="cancel", description="لغو عملیات جاری"),
        BotCommand(command="help", description="راهنما"),
    ])

    app = make_app(db, bot, settings, zarinpal)
    app["bot_username"] = me.username or ""
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, settings.web_host, settings.web_port).start()
    log.info("http server on %s:%s (/health%s)", settings.web_host, settings.web_port,
             ", /pay/callback" if zarinpal else "")

    reminders = asyncio.create_task(reminder_loop(bot, db))
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, f"✅ ربات @{me.username} روشن شد.")
        except Exception:
            log.info("startup notice to %s failed", admin_id)
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
