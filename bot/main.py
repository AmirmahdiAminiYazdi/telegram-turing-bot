from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from bot.config import load_settings
from bot.db import Database
from bot.handlers import admin, user
from bot.services.zarinpal import Zarinpal
from bot.web import make_app


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    db = Database(settings.db_path)
    await db.connect()

    bot = Bot(settings.bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    zarinpal = (Zarinpal(settings.zarinpal_merchant_id, settings.zarinpal_sandbox)
                if settings.zarinpal_enabled else None)

    dp = Dispatcher(storage=MemoryStorage(), db=db, settings=settings, zarinpal=zarinpal)
    dp.include_router(admin.router)  # قبل از کاربر تا فیلتر ادمین/وضعیت‌ها اولویت داشته باشد
    dp.include_router(user.router)

    runner = None
    if zarinpal:
        app = make_app(db, bot, settings, zarinpal)
        app["bot_username"] = (await bot.me()).username or ""
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, settings.web_host, settings.web_port).start()
        logging.info("callback server on %s:%s", settings.web_host, settings.web_port)

    try:
        await dp.start_polling(bot)
    finally:
        if runner:
            await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
