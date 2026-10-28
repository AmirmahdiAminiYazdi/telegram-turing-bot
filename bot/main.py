from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web

from bot.config import load_settings
from bot.db import Database
from bot.handlers import admin, admin_more, user
from bot.middlewares import ForceSub, Throttle
from bot.services.reminders import reminder_loop
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
    # ترتیب مهم است: روترهای ادمین قبل از کاربر
    dp.include_router(admin.router)
    dp.include_router(admin_more.router)
    dp.include_router(user.router)
    throttle = Throttle()
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)
    user.router.message.middleware(ForceSub())
    user.router.callback_query.middleware(ForceSub())

    await bot.set_my_commands([
        BotCommand(command="start", description="شروع و منوی اصلی"),
        BotCommand(command="cancel", description="لغو عملیات جاری"),
        BotCommand(command="help", description="راهنما"),
    ])
    reminders = asyncio.create_task(reminder_loop(bot, db))

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
        reminders.cancel()
        if runner:
            await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
