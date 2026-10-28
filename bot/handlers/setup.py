"""راه‌اندازی اولیه: وقتی هیچ ادمینی تعریف نشده، اولین نفری که کد لاگ را بفرستد ادمین می‌شود."""
from __future__ import annotations

import hmac
import logging
import secrets
import time

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import Settings
from bot.db import Database

log = logging.getLogger(__name__)
router = Router(name="setup")

MAX_ATTEMPTS = 5
LOCK_SECONDS = 600


class ClaimGate:
    """کد یک‌بارمصرف ادمین‌شدن؛ فقط تا وقتی ادمینی نیست فعال است و حدس زدن قفل می‌شود."""

    def __init__(self, code: str | None = None, clock=time.monotonic):
        self.code = code or secrets.token_urlsafe(9)
        self.clock = clock
        self.fails = 0
        self.locked_until = 0.0

    def try_claim(self, supplied: str) -> bool:
        now = self.clock()
        if now < self.locked_until:
            return False
        if hmac.compare_digest(supplied.encode(), self.code.encode()):
            self.fails = 0
            return True
        self.fails += 1
        if self.fails >= MAX_ATTEMPTS:
            self.fails, self.locked_until = 0, now + LOCK_SECONDS
        return False


@router.message(Command("claim"))
async def claim(message: Message, command: CommandObject, settings: Settings,
                db: Database, claim_gate: ClaimGate | None) -> None:
    if settings.admin_ids or claim_gate is None:
        return  # بعد از تعیین ادمین، این فرمان وجود ندارد
    if not claim_gate.try_claim((command.args or "").strip()):
        await message.answer("کد معتبر نیست.")
        return
    uid = message.from_user.id
    settings.admin_ids.add(uid)
    await db.set_setting("extra_admins", ",".join(str(i) for i in sorted(settings.admin_ids)))
    log.warning("first admin claimed: %s", uid)
    await message.answer("✅ تو ادمین هستی. /admin را بزن.")
