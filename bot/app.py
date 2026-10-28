"""ساخت Dispatcher نهایی؛ هم main و هم تست‌ها از همین‌جا استفاده می‌کنند تا سیم‌کشی واقعی تست شود."""
from __future__ import annotations

import logging
import time
from html import escape

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, admin_more, setup, user
from bot.handlers.setup import ClaimGate
from bot.middlewares import ForceSub, Throttle
from bot.services.zarinpal import Zarinpal
from bot.storage import SqliteStorage

log = logging.getLogger(__name__)

ERROR_NOTIFY_EVERY = 300  # ثانیه؛ طوفان خطا اعلان‌های ادمین را پر نکند


def create_dispatcher(db: Database, settings: Settings, zarinpal: Zarinpal | None,
                      claim_gate: ClaimGate | None = None) -> Dispatcher:
    dp = Dispatcher(storage=SqliteStorage(db), db=db, settings=settings,
                    zarinpal=zarinpal, claim_gate=claim_gate)
    # ترتیب مهم است: setup و ادمین قبل از کاربر
    for router in (setup.router, admin.router, admin_more.router, user.router):
        dp.include_router(router)
    throttle = Throttle(settings.throttle_seconds)
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)
    user.router.message.middleware(ForceSub())
    user.router.callback_query.middleware(ForceSub())

    last_notified: dict[str, float] = {}

    @dp.errors()
    async def on_error(event: ErrorEvent, bot, settings: Settings) -> bool:
        exc = event.exception
        log.exception("unhandled error", exc_info=exc)
        name = type(exc).__name__
        now = time.monotonic()
        if now - last_notified.get(name, -1e9) >= ERROR_NOTIFY_EVERY:
            last_notified[name] = now
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(
                        admin_id, f"⚠️ خطای ربات: <code>{escape(name)}</code>\n"
                                  f"{escape(str(exc))[:300]}\nجزئیات در لاگ سرور.")
                except Exception:
                    pass
        return True

    return dp
