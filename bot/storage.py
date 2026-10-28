"""FSM ماندگار روی SQLite: بعد از ری‌استارت یا آپدیت ربات، گفتگوهای نیمه‌کاره (ساخت محصول،
کد تخفیف، پیام به پشتیبانی) از بین نمی‌روند."""
from __future__ import annotations

import json
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from bot.db import Database


def _key(k: StorageKey) -> str:
    return ":".join(str(x) for x in (k.bot_id, k.chat_id, k.user_id, k.thread_id,
                                      k.business_connection_id, k.destiny))


class SqliteStorage(BaseStorage):
    def __init__(self, db: Database):
        self.db = db

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        row = await self.db.fsm_get(_key(key))
        await self.db.fsm_put(_key(key), value, row["data"] if row else "{}")

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self.db.fsm_get(_key(key))
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        row = await self.db.fsm_get(_key(key))
        state = row["state"] if row else None
        if not data and state is None:
            await self.db.fsm_delete(_key(key))  # جدول بی‌خود بزرگ نشود
            return
        await self.db.fsm_put(_key(key), state, json.dumps(data, ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self.db.fsm_get(_key(key))
        return json.loads(row["data"]) if row else {}

    async def close(self) -> None:  # اتصال دیتابیس را main می‌بندد
        return None
