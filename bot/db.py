from __future__ import annotations

import os
from typing import Any

import aiosqlite

SCHEMA_V1 = """
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
# paid -> refunded

SCHEMA_V2 = """
ALTER TABLE orders ADD COLUMN original_amount INTEGER;
ALTER TABLE orders ADD COLUMN discount_code TEXT;
ALTER TABLE orders ADD COLUMN reminded INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS discounts (
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                  -- percent | fixed
    value INTEGER NOT NULL,
    max_uses INTEGER,                    -- NULL = نامحدود
    used INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,                     -- NULL = بدون انقضا
    product_id INTEGER,                  -- NULL = همه دوره‌ها
    owner_id INTEGER                     -- NULL = همه؛ وگرنه فقط همین کاربر
);
CREATE TABLE IF NOT EXISTS referrals (
    referee_id INTEGER PRIMARY KEY,
    referrer_id INTEGER NOT NULL,
    rewarded INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS support_map (
    admin_chat INTEGER NOT NULL,
    admin_msg INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (admin_chat, admin_msg)
);
"""

MIGRATIONS = {1: SCHEMA_V1, 2: SCHEMA_V2}


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
        await self._migrate()

    async def _migrate(self) -> None:
        """نسخه‌ی اسکیما در PRAGMA user_version؛ هر مهاجرت فقط یک‌بار اجرا می‌شود."""
        async with self._conn.execute("PRAGMA user_version") as cur:
            current = (await cur.fetchone())[0]
        for version in sorted(MIGRATIONS):
            if version > current:
                await self._conn.executescript(MIGRATIONS[version])
                await self._conn.execute(f"PRAGMA user_version = {version}")
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
                          full_name: str, source: str | None = None) -> bool:
        """True اگر کاربر جدید بود."""
        is_new = await self._one("SELECT 1 FROM users WHERE id=?", (user_id,)) is None
        await self._exec(
            """INSERT INTO users(id, username, full_name, source) VALUES(?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET username=excluded.username,
               full_name=excluded.full_name""",
            (user_id, username, full_name, source),
        )
        return is_new

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
    async def create_order(self, user_id: int, product: dict[str, Any], method: str,
                           amount: int | None = None,
                           discount_code: str | None = None) -> int:
        cur = await self._exec(
            "INSERT INTO orders(user_id, product_id, amount, original_amount, method,"
            " discount_code) VALUES(?,?,?,?,?,?)",
            (user_id, product["id"], product["price"] if amount is None else amount,
             product["price"], method, discount_code),
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
            " paid_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('pending','receipt_sent')",
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

    # ---- settings ----
    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._exec(
            "INSERT INTO settings(key, value) VALUES(?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ---- discounts ----
    async def create_discount(self, code: str, kind: str, value: int,
                              max_uses: int | None = None, days: int | None = None,
                              product_id: int | None = None,
                              owner_id: int | None = None) -> bool:
        expires = f"+{int(days)} days" if days else None
        try:
            await self._exec(
                "INSERT INTO discounts(code, kind, value, max_uses, expires_at,"
                " product_id, owner_id) VALUES(?,?,?,?,"
                " CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END, ?, ?)",
                (code.upper(), kind, value, max_uses, expires, expires, product_id, owner_id))
        except aiosqlite.IntegrityError:
            return False
        return True

    async def get_discount(self, code: str) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM discounts WHERE code=?", (code.upper(),))

    async def list_discounts(self) -> list[dict[str, Any]]:
        return await self._all("SELECT * FROM discounts ORDER BY rowid DESC LIMIT 50")

    async def delete_discount(self, code: str) -> bool:
        cur = await self._exec("DELETE FROM discounts WHERE code=?", (code.upper(),))
        return cur.rowcount == 1

    async def reserve_discount(self, code: str) -> bool:
        """یک استفاده را اتمیک رزرو می‌کند؛ False یعنی ظرفیت تمام شده یا منقضی است."""
        cur = await self._exec(
            "UPDATE discounts SET used = used + 1 WHERE code=?"
            " AND (max_uses IS NULL OR used < max_uses)"
            " AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (code.upper(),))
        return cur.rowcount == 1

    async def release_discount(self, code: str) -> None:
        await self._exec(
            "UPDATE discounts SET used = MAX(used - 1, 0) WHERE code=?", (code.upper(),))

    # ---- referrals ----
    async def add_referral(self, referee_id: int, referrer_id: int) -> bool:
        if referee_id == referrer_id or not await self._one(
                "SELECT 1 FROM users WHERE id=?", (referrer_id,)):
            return False
        cur = await self._exec(
            "INSERT OR IGNORE INTO referrals(referee_id, referrer_id) VALUES(?,?)",
            (referee_id, referrer_id))
        return cur.rowcount == 1

    async def get_referral(self, referee_id: int) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM referrals WHERE referee_id=?", (referee_id,))

    async def claim_referral_reward(self, referee_id: int) -> int | None:
        """referrer_id را فقط برای اولین پاداش برمی‌گرداند (اتمیک)."""
        ref = await self.get_referral(referee_id)
        if not ref:
            return None
        cur = await self._exec(
            "UPDATE referrals SET rewarded=1 WHERE referee_id=? AND rewarded=0",
            (referee_id,))
        return ref["referrer_id"] if cur.rowcount == 1 else None

    async def referral_stats(self, referrer_id: int) -> dict[str, int]:
        row = await self._one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(rewarded),0) AS r FROM referrals"
            " WHERE referrer_id=?", (referrer_id,))
        return {"invited": row["n"], "converted": row["r"]}

    # ---- support relay ----
    async def add_support_msg(self, admin_chat: int, admin_msg: int, user_id: int) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO support_map(admin_chat, admin_msg, user_id)"
            " VALUES(?,?,?)", (admin_chat, admin_msg, user_id))

    async def support_user(self, admin_chat: int, admin_msg: int) -> int | None:
        row = await self._one(
            "SELECT user_id FROM support_map WHERE admin_chat=? AND admin_msg=?",
            (admin_chat, admin_msg))
        return row["user_id"] if row else None

    # ---- reminders ----
    async def due_reminders(self, after_hours: int = 2, max_hours: int = 48) -> list[dict[str, Any]]:
        """سفارش‌های رهاشده: pending، بدون پرداخت همان دوره و هنوز یادآوری نشده."""
        return await self._all(
            "SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id"
            " WHERE o.status='pending' AND o.reminded=0"
            " AND o.created_at <= datetime('now', ?) AND o.created_at > datetime('now', ?)"
            " AND NOT EXISTS (SELECT 1 FROM orders x WHERE x.user_id=o.user_id"
            "   AND x.product_id=o.product_id AND x.status='paid')"
            " GROUP BY o.user_id, o.product_id",
            (f"-{after_hours} hours", f"-{max_hours} hours"))

    async def mark_reminded(self, user_id: int, product_id: int) -> None:
        await self._exec(
            "UPDATE orders SET reminded=1 WHERE user_id=? AND product_id=?"
            " AND status='pending'", (user_id, product_id))

    # ---- admin: orders / reports ----
    async def order_details(self, order_id: int) -> dict[str, Any] | None:
        return await self._one(
            "SELECT o.*, p.title, p.channel_id, u.username, u.full_name FROM orders o"
            " JOIN products p ON p.id=o.product_id LEFT JOIN users u ON u.id=o.user_id"
            " WHERE o.id=?", (order_id,))

    async def refund_order(self, order_id: int) -> bool:
        cur = await self._exec(
            "UPDATE orders SET status='refunded' WHERE id=? AND status='paid'", (order_id,))
        return cur.rowcount == 1

    async def recent_orders(self, limit: int = 15) -> list[dict[str, Any]]:
        return await self._all(
            "SELECT o.*, p.title FROM orders o JOIN products p ON p.id=o.product_id"
            " ORDER BY o.id DESC LIMIT ?", (limit,))

    async def all_orders(self) -> list[dict[str, Any]]:
        return await self._all(
            "SELECT o.id, o.user_id, p.title, o.amount, o.original_amount,"
            " o.discount_code, o.method, o.status, o.ref_id, o.created_at, o.paid_at,"
            " u.source FROM orders o JOIN products p ON p.id=o.product_id"
            " LEFT JOIN users u ON u.id=o.user_id ORDER BY o.id")

    async def revenue_since(self, days: int) -> int:
        row = await self._one(
            "SELECT COALESCE(SUM(amount),0) AS s FROM orders WHERE status='paid'"
            " AND paid_at >= datetime('now', ?)", (f"-{days} days",))
        return row["s"]

    async def sources_report(self, limit: int = 10) -> list[dict[str, Any]]:
        """کاربر و خرید به تفکیک منبع ورود (مقدار ?start=)."""
        return await self._all(
            "SELECT COALESCE(u.source, '(مستقیم)') AS source, COUNT(DISTINCT u.id) AS users,"
            " COUNT(DISTINCT CASE WHEN o.status='paid' THEN o.id END) AS paid"
            " FROM users u LEFT JOIN orders o ON o.user_id=u.id"
            " GROUP BY 1 ORDER BY users DESC LIMIT ?", (limit,))

    async def update_product(self, product_id: int, field: str, value: Any) -> None:
        if field not in {"title", "description", "price", "channel_id", "access_text"}:
            raise ValueError(field)
        await self._exec(f"UPDATE products SET {field}=? WHERE id=?", (value, product_id))
