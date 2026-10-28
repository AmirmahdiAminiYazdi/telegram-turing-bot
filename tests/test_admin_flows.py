"""مسیرهای پنل ادمین و بخش‌های کمتر پوشش‌داده‌ی کاربر، با همان سیم‌کشی تولید."""
from unittest.mock import AsyncMock

from tests.helpers import ADMIN, BUYER, _product, say, tap


def sent_docs(c):
    return [p for n, p in c.bot.calls if n == "SendDocument"]


async def test_create_product_wizard(ctx):
    await tap(ctx, ADMIN, "adm:new")
    await say(ctx, ADMIN, "دوره پایتون")
    await say(ctx, ADMIN, "از صفر تا پروژه")
    await say(ctx, ADMIN, "abc")  # قیمت نامعتبر: مرحله جلو نمی‌رود
    assert any("عدد معتبر نیست" in t for t in ctx.bot.texts(ADMIN))
    await say(ctx, ADMIN, "۱٬۲۰۰٬۰۰۰")
    await say(ctx, ADMIN, "x1")  # آیدی کانال نامعتبر
    assert any("عددی نیست" in t for t in ctx.bot.texts(ADMIN))
    await say(ctx, ADMIN, "-1001234567890")
    await say(ctx, ADMIN, "LINK-XYZ")
    p = (await ctx.db.list_products(only_active=False))[0]
    assert (p["title"], p["price"], p["channel_id"], p["access_text"]) == (
        "دوره پایتون", 1_200_000, -1001234567890, "LINK-XYZ")


async def test_wizard_dash_means_empty_and_cancel_clears(ctx):
    await tap(ctx, ADMIN, "adm:new")
    await say(ctx, ADMIN, "الف")
    await say(ctx, ADMIN, "ب")
    await say(ctx, ADMIN, "5000")
    await say(ctx, ADMIN, "-")
    await say(ctx, ADMIN, "-")
    p = (await ctx.db.list_products(only_active=False))[0]
    assert p["channel_id"] is None and p["access_text"] is None
    await tap(ctx, ADMIN, "adm:new")
    await say(ctx, ADMIN, "/cancel")
    await say(ctx, ADMIN, "متن بی‌ربط")  # دیگر در ویزارد نیست
    assert len(await ctx.db.list_products(only_active=False)) == 1


async def test_product_list_toggle_delete_rules(ctx):
    pid = await _product(ctx)
    await tap(ctx, ADMIN, "adm:products")
    await tap(ctx, ADMIN, f"adm:p:{pid}")
    await tap(ctx, ADMIN, f"adm:tog:{pid}")
    assert (await ctx.db.get_product(pid))["active"] == 0
    # محصول دارای سفارش حذف نمی‌شود
    await ctx.db.upsert_user(BUYER, None, "b")
    await ctx.db.create_order(BUYER, await ctx.db.get_product(pid), "card")
    await tap(ctx, ADMIN, f"adm:del:{pid}")
    assert any("سفارش دارد" in a for a in ctx.bot.alerts())
    empty = await _product(ctx)
    await tap(ctx, ADMIN, f"adm:del:{empty}")
    assert await ctx.db.get_product(empty) is None


async def test_license_codes_upload_and_delivery(ctx):
    pid = await ctx.db.add_product("د", "d", 1000, None, None)
    await tap(ctx, ADMIN, f"adm:codes:{pid}")
    await say(ctx, ADMIN, "K1\n\n K2 \nK3")
    assert await ctx.db.free_codes_count(pid) == 3


async def test_edit_basic_fields_and_validation(ctx):
    pid = await _product(ctx)
    for field, value in (("title", "عنوان جدید"), ("description", "توضیح جدید"), ("price", "۲۵۰۰۰۰"),
                         ("channel_id", "-100777"), ("access_text", "ACCESS"), ("guarantee", "ضمانت"),
                         ("preview_url", "https://x.ir/p")):
        await tap(ctx, ADMIN, f"adm:ed:{field}:{pid}")
        await say(ctx, ADMIN, value)
    p = await ctx.db.get_product(pid)
    assert (p["title"], p["description"], p["price"], p["channel_id"]) == (
        "عنوان جدید", "توضیح جدید", 250_000, -100777)
    assert (p["access_text"], p["guarantee"], p["preview_url"]) == ("ACCESS", "ضمانت", "https://x.ir/p")

    await tap(ctx, ADMIN, f"adm:ed:price:{pid}")
    await say(ctx, ADMIN, "صفر")  # نامعتبر، مقدار تغییر نمی‌کند
    await say(ctx, ADMIN, "/cancel")
    assert (await ctx.db.get_product(pid))["price"] == 250_000
    for field in ("channel_id", "access_text", "guarantee"):  # خط تیره = حذف
        await tap(ctx, ADMIN, f"adm:ed:{field}:{pid}")
        await say(ctx, ADMIN, "-")
    p = await ctx.db.get_product(pid)
    assert p["channel_id"] is None and p["access_text"] is None and p["guarantee"] is None


async def test_discount_wizard_and_delete(ctx):
    await tap(ctx, ADMIN, "adm:dnew")
    await say(ctx, ADMIN, "bad code!")  # کاراکتر نامجاز
    await say(ctx, ADMIN, "summer")
    await say(ctx, ADMIN, "150%")  # بیش از ۱۰۰ درصد رد می‌شود
    await say(ctx, ADMIN, "20%")
    await say(ctx, ADMIN, "0")
    await say(ctx, ADMIN, "10")
    await say(ctx, ADMIN, "30")
    d = await ctx.db.get_discount("SUMMER")
    assert (d["kind"], d["value"], d["max_uses"]) == ("percent", 20, 10) and d["expires_at"]
    await tap(ctx, ADMIN, "adm:discounts")
    await tap(ctx, ADMIN, "adm:ddel:SUMMER")
    assert await ctx.db.get_discount("SUMMER") is None

    await tap(ctx, ADMIN, "adm:dnew")
    await say(ctx, ADMIN, "-")  # نام خودکار
    await say(ctx, ADMIN, "50000")
    await say(ctx, ADMIN, "-")
    await say(ctx, ADMIN, "-")
    codes = await ctx.db.list_discounts()
    assert codes[0]["code"].startswith("OFF-") and codes[0]["kind"] == "fixed"
    assert codes[0]["max_uses"] is None and codes[0]["expires_at"] is None


async def test_order_admin_view_resend_refund_export(ctx):
    pid = await ctx.db.add_product("د", "d", 80_000, -1009, "ACC")
    await ctx.db.upsert_user(BUYER, "buyer", "Buyer")
    oid = await ctx.db.create_order(BUYER, await ctx.db.get_product(pid), "card")
    await ctx.db.mark_paid(oid, "REF")
    await tap(ctx, ADMIN, "adm:orders")
    await tap(ctx, ADMIN, f"adm:o:{oid}")
    assert any("REF" in t and "@buyer" in t for t in ctx.bot.texts(ADMIN))
    await say(ctx, ADMIN, f"/order {oid}")
    await say(ctx, ADMIN, "/order")  # بدون شماره: راهنما
    assert any("/order 123" in t for t in ctx.bot.texts(ADMIN))

    await tap(ctx, ADMIN, f"adm:resend:{oid}")
    assert any("ACC" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, ADMIN, f"adm:refund:{oid}")
    assert (await ctx.db.get_order(oid))["status"] == "refunded"
    names = [n for n, _ in ctx.bot.calls]
    assert "BanChatMember" in names and "UnbanChatMember" in names  # حذف از کانال بدون مسدود ماندن
    assert any("استرداد شد" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, ADMIN, f"adm:refund:{oid}")  # دوباره: بی‌اثر
    assert any("قابل استرداد نیست" in a for a in ctx.bot.alerts())
    await tap(ctx, ADMIN, f"adm:resend:{oid}")
    assert any("پرداخت‌شده نیست" in a for a in ctx.bot.alerts())

    await tap(ctx, ADMIN, "adm:export")
    doc = sent_docs(ctx)[0]["document"]
    assert doc.filename == "orders.csv"
    body = doc.data.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("id,user_id,course") and "REF" in body


async def test_pending_receipts_listing_and_stats(ctx):
    pid = await _product(ctx)
    await tap(ctx, ADMIN, "adm:pending")
    assert any("رسید منتظری نیست" in a for a in ctx.bot.alerts())
    await ctx.db.upsert_user(BUYER, None, "b")
    oid = await ctx.db.create_order(BUYER, await ctx.db.get_product(pid), "card")
    await ctx.db.set_receipt(oid, "FILE")
    await tap(ctx, ADMIN, "adm:pending")
    assert any(n == "SendPhoto" and p["photo"] == "FILE" for n, p in ctx.bot.calls)
    await tap(ctx, ADMIN, "adm:stats")
    assert any("منبع ورود" in t for t in ctx.bot.texts(ADMIN))


async def test_broadcast_counts_successes_and_failures(ctx):
    for uid in (1, 2, 3):
        await ctx.db.upsert_user(uid, None, "x")
    original = ctx.bot.send_message
    async def flaky(chat_id, text, **kw):
        if chat_id == 2:
            raise RuntimeError("blocked")
        return await original(chat_id, text, **kw)
    ctx.bot.send_message = flaky
    await tap(ctx, ADMIN, "adm:bc")
    await say(ctx, ADMIN, "سلام همگانی")
    assert any("ارسال شد: 2" in t and "ناموفق: 1" in t for t in ctx.bot.texts(ADMIN))


async def test_non_admin_cannot_use_admin_callbacks(ctx):
    pid = await _product(ctx)
    for data in (f"adm:tog:{pid}", f"adm:del:{pid}", "adm:export", "adm:stats", "adm:bc"):
        await tap(ctx, BUYER, data)
    assert (await ctx.db.get_product(pid))["active"] == 1
    assert not sent_docs(ctx)
    await say(ctx, BUYER, "/set force_channel @evil")
    await say(ctx, BUYER, f"/sale {pid} 1 1")
    assert await ctx.db.get_setting("force_channel") == ""
    assert (await ctx.db.get_product(pid))["on_sale"] == 0


# ---- کاربر: مسیرهای باقی‌مانده ----
async def test_zarinpal_flow_via_bot(ctx):
    from dataclasses import replace

    from bot.app import create_dispatcher
    from bot.handlers import admin, admin_more, setup, user

    zp = AsyncMock()
    zp.request.return_value = ("AUTH9", "https://pay.example/AUTH9")
    settings = replace(ctx.settings, zarinpal_merchant_id="M", public_base_url="https://x.ir")
    for r in (setup.router, admin.router, admin_more.router, user.router):
        r._parent_router = None  # روترها singleton ماژول‌اند؛ برای Dispatcher دوم جدا می‌شوند
    user.router.message.middleware._middlewares.clear()
    user.router.callback_query.middleware._middlewares.clear()
    ctx.dp = create_dispatcher(ctx.db, settings, zp)

    pid = await _product(ctx, 100_000)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"pay:z:{pid}")
    order = await ctx.db._one("SELECT * FROM orders")
    assert order["authority"] == "AUTH9" and order["method"] == "zarinpal"
    zp.request.assert_awaited_once()
    assert zp.request.await_args.args[0] == 100_000
    assert zp.request.await_args.args[1] == "https://x.ir/pay/callback"
    assert any(n == "EditMessageText" and "pay.example" in str(p["reply_markup"]) for n, p in ctx.bot.calls)

    cheap = await _product(ctx, 500)  # زیر حداقل زرین‌پال
    await tap(ctx, BUYER, f"pay:z:{cheap}")
    assert any("۱٬۰۰۰ تومان" in a for a in ctx.bot.alerts())
    assert await ctx.db.paid_order(BUYER, cheap) is None


async def test_mine_again_support_ref_and_inactive_product(ctx):
    pid = await ctx.db.add_product("دوره", "d", 1000, None, "ACC")
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, "mine")
    assert any("هنوز دوره‌ای نخریده" in t for t in ctx.bot.texts(BUYER))
    oid = await ctx.db.create_order(BUYER, await ctx.db.get_product(pid), "card")
    await ctx.db.mark_paid(oid)
    await tap(ctx, BUYER, "mine")
    await tap(ctx, BUYER, f"again:{oid}")
    assert any("ACC" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, 777, f"again:{oid}")  # سفارش دیگری
    assert not any("ACC" in t for t in ctx.bot.texts(777))

    await tap(ctx, BUYER, f"buy:{pid}")  # قبلاً خریده: فقط دسترسی دوباره
    assert any("قبلاً خریده" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, BUYER, "support")
    await tap(ctx, BUYER, "ref")
    assert any("ref_" in t for t in ctx.bot.texts(BUYER))

    await ctx.db.toggle_product(pid)
    await tap(ctx, 888, f"p:{pid}")
    assert any("دوره‌ای" in a or "فروش" in a for a in ctx.bot.alerts())
    await tap(ctx, 888, "catalog")
    assert any("دوره‌ای برای فروش" in t for t in ctx.bot.texts(888))
