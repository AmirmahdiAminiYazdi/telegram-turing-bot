from __future__ import annotations

import os
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL,              -- تومان
    channel_id INTEGER,                  -- کانال/گروه خصوصی برای لینک یک‌بارمصرف
    access_text TEXT,                    -- متن/لینک/کد دسترسی ثابت
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    order_id INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    amount INTEGER NOT NULL,             -- تومان
    method TEXT NOT NULL,                -- zarinpal | card
    status TEXT NOT NULL DEFAULT 'pending',
    authority TEXT,
    ref_id TEXT,
    receipt_file_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_authority ON orders(authority);
"""

# وضعیت‌ها: pending (ساخته شد) -> receipt_sent (فقط کارت) -> paid | rejected


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    async def _one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _exec(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    # ---- users ----
    async def upsert_user(self, user_id: int, username: str | None,
                          full_name: str, source: str | None = None) -> None:
        await self._exec(
            """INSERT INTO users(id, username, full_name, source) VALUES(?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET username=excluded.username,
               full_name=excluded.full_name""",
            (user_id, username, full_name, source),
        )

    async def user_ids(self) -> list[int]:
        return [r["id"] for r in await self._all("SELECT id FROM users")]

    # ---- products ----
    async def add_product(self, title: str, description: str, price: int,
                          channel_id: int | None, access_text: str | None) -> int:
        cur = await self._exec(
            "INSERT INTO products(title, description, price, channel_id, access_text)"
            " VALUES(?,?,?,?,?)",
            (title, description, price, channel_id, access_text),
        )
        return cur.lastrowid

    async def get_product(self, product_id: int) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM products WHERE id=?", (product_id,))

    async def list_products(self, only_active: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM products"
        if only_active:
            sql += " WHERE active=1"
        return await self._all(sql + " ORDER BY id")

    async def toggle_product(self, product_id: int) -> None:
        await self._exec("UPDATE products SET active = 1 - active WHERE id=?",
                         (product_id,))

    async def delete_product(self, product_id: int) -> bool:
        """محصولی که سفارش دارد حذف نمی‌شود (فقط غیرفعال شود)."""
        if await self._one("SELECT 1 FROM orders WHERE product_id=?", (product_id,)):
            return False
        await self._exec("DELETE FROM products WHERE id=?", (product_id,))
        return True

    # ---- codes ----
    async def add_codes(self, product_id: int, codes: list[str]) -> int:
        await self.conn.executemany(
            "INSERT INTO codes(product_id, code) VALUES(?,?)",
            [(product_id, c) for c in codes],
        )
        await self.conn.commit()
        return len(codes)

    async def free_codes_count(self, product_id: int) -> int:
        row = await self._one(
            "SELECT COUNT(*) AS n FROM codes WHERE product_id=? AND order_id IS NULL",
            (product_id,))
        return row["n"]

    async def claim_code(self, product_id: int, order_id: int) -> str | None:
        """یک کد آزاد را اتمیک به سفارش اختصاص می‌دهد (اگر قبلا گرفته، همان را برمی‌گرداند)."""
        existing = await self._one(
            "SELECT code FROM codes WHERE order_id=?", (order_id,))
        if existing:
            return existing["code"]
        row = await self._one(
            "SELECT id, code FROM codes WHERE product_id=? AND order_id IS NULL"
            " ORDER BY id LIMIT 1", (product_id,))
        if not row:
            return None
        cur = await self._exec(
            "UPDATE codes SET order_id=? WHERE id=? AND order_id IS NULL",
            (order_id, row["id"]))
        if cur.rowcount == 0:
            return await self.claim_code(product_id, order_id)
        return row["code"]

    # ---- orders ----
    async def create_order(self, user_id: int, product: dict[str, Any],
                           method: str) -> int:
        cur = await self._exec(
            "INSERT INTO orders(user_id, product_id, amount, method) VALUES(?,?,?,?)",
            (user_id, product["id"], product["price"], method),
        )
        return cur.lastrowid

    async def get_order(self, order_id: int) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM orders WHERE id=?", (order_id,))

    async def get_order_by_authority(self, authority: str) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM orders WHERE authority=?", (authority,))

    async def set_authority(self, order_id: int, authority: str) -> None:
        await self._exec("UPDATE orders SET authority=? WHERE id=?",
                         (authority, order_id))

    async def set_receipt(self, order_id: int, file_id: str) -> bool:
        cur = await self._exec(
            "UPDATE orders SET receipt_file_id=?, status='receipt_sent'"
            " WHERE id=? AND method='card' AND status IN ('pending','receipt_sent')",
            (file_id, order_id))
        return cur.rowcount == 1

    async def mark_paid(self, order_id: int, ref_id: str | None = None) -> bool:
        """True فقط برای اولین تبدیل به paid؛ جلوی تحویل دوباره را می‌گیرد."""
        cur = await self._exec(
            "UPDATE orders SET status='paid', ref_id=COALESCE(?, ref_id),"
            " paid_at=CURRENT_TIMESTAMP WHERE id=? AND status!='paid'",
            (ref_id, order_id))
        return cur.rowcount == 1

    async def reject_order(self, order_id: int) -> bool:
        cur = await self._exec(
            "UPDATE orders SET status='rejected' WHERE id=? AND status='receipt_sent'",
            (order_id,))
        return cur.rowcount == 1

    async def paid_order(self, user_id: int, product_id: int) -> dict[str, Any] | None:
        return await self._one(
            "SELECT * FROM orders WHERE user_id=? AND product_id=? AND status='paid'"
            " ORDER BY id DESC LIMIT 1", (user_id, product_id))

    async def user_paid_orders(self, user_id: int) -> list[dict[str, Any]]:
        return await self._all(
            "SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id"
            " WHERE o.user_id=? AND o.status='paid' ORDER BY o.id DESC", (user_id,))

    async def pending_receipts(self) -> list[dict[str, Any]]:
        return await self._all(
            "SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id"
            " WHERE o.status='receipt_sent' ORDER BY o.id")

    async def stats(self) -> dict[str, int]:
        users = await self._one("SELECT COUNT(*) AS n FROM users")
        paid = await self._one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS s FROM orders"
            " WHERE status='paid'")
        started = await self._one("SELECT COUNT(*) AS n FROM orders")
        return {"users": users["n"], "orders": started["n"],
                "paid": paid["n"], "revenue": paid["s"]}
