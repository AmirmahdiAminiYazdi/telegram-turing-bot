"""مسیرهای واقعی dispatcher (فیلترها، FSM، middlewareها) با Bot جعلی."""
from datetime import datetime

from aiogram.types import Chat, Message, Update, User

from bot.config import Settings
from bot.middlewares import Throttle
from tests.helpers import ADMIN, BUYER, _product, photo, say, tap


async def test_start_registers_user_and_admin_gate(ctx):
    await say(ctx, BUYER, "/start ad_instagram")
    assert (await ctx.db._one("SELECT source FROM users WHERE id=?", (BUYER,)))["source"] == "ad_instagram"
    await say(ctx, BUYER, "/admin")
    assert not any("پنل ادمین" in t for t in ctx.bot.texts(BUYER))
    await say(ctx, ADMIN, "/admin")
    assert any("پنل ادمین" in t for t in ctx.bot.texts(ADMIN))


async def test_card_purchase_with_discount_end_to_end(ctx):
    pid = await _product(ctx)
    await ctx.db.create_discount("HALF", "percent", 50)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"buy:{pid}")
    await tap(ctx, BUYER, f"disc:{pid}")
    await say(ctx, BUYER, "half")
    assert any("50,000" in t for t in ctx.bot.texts(BUYER))  # قیمت جدید نمایش داده شد
    await tap(ctx, BUYER, f"pay:c:{pid}")
    order = await ctx.db._one("SELECT * FROM orders")
    assert order["amount"] == 50_000 and order["original_amount"] == 100_000
    assert order["discount_code"] == "HALF"
    assert (await ctx.db.get_discount("HALF"))["used"] == 1

    await photo(ctx, BUYER)
    assert any(n == "SendPhoto" and p["chat_id"] == ADMIN for n, p in ctx.bot.calls)
    await tap(ctx, ADMIN, f"adm:ok:{order['id']}", caption="رسید")
    assert (await ctx.db.get_order(order["id"]))["status"] == "paid"
    assert any("LINK-123" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, ADMIN, f"adm:ok:{order['id']}", caption="رسید")  # دوبار کلیک
    assert sum("LINK-123" in t for t in ctx.bot.texts(BUYER)) == 1


async def test_invalid_discount_keeps_state_and_cancel_exits(ctx):
    pid = await _product(ctx)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"disc:{pid}")
    await say(ctx, BUYER, "WRONG")
    assert any("معتبر نیست" in t for t in ctx.bot.texts(BUYER))
    await say(ctx, BUYER, "/cancel")
    assert any("لغو شد" in t for t in ctx.bot.texts(BUYER))


async def test_free_order_with_full_discount(ctx):
    pid = await _product(ctx)
    await ctx.db.create_discount("FREE", "percent", 100)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"disc:{pid}")
    await say(ctx, BUYER, "FREE")
    await tap(ctx, BUYER, f"pay:c:{pid}")
    order = await ctx.db._one("SELECT * FROM orders")
    assert order["status"] == "paid" and order["amount"] == 0
    assert any("LINK-123" in t for t in ctx.bot.texts(BUYER))


async def test_rejected_order_releases_discount(ctx):
    pid = await _product(ctx)
    await ctx.db.create_discount("ONE", "fixed", 1000, max_uses=1)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"disc:{pid}")
    await say(ctx, BUYER, "ONE")
    await tap(ctx, BUYER, f"pay:c:{pid}")
    await photo(ctx, BUYER)
    oid = (await ctx.db._one("SELECT id FROM orders"))["id"]
    await tap(ctx, ADMIN, f"adm:no:{oid}", caption="رسید")
    assert (await ctx.db.get_discount("ONE"))["used"] == 0


async def test_referral_link_and_reward_flow(ctx):
    pid = await _product(ctx)
    await say(ctx, 55, "/start")  # معرف
    await say(ctx, BUYER, "/start ref_55")
    assert (await ctx.db.get_referral(BUYER))["referrer_id"] == 55
    await say(ctx, 66, "/start ref_55")
    await say(ctx, BUYER, "/start ref_66")  # کاربر قدیمی: معرف عوض نمی‌شود
    assert (await ctx.db.get_referral(BUYER))["referrer_id"] == 55

    await tap(ctx, BUYER, f"pay:c:{pid}")
    oid = (await ctx.db._one("SELECT id FROM orders"))["id"]
    await photo(ctx, BUYER)
    await tap(ctx, ADMIN, f"adm:ok:{oid}", caption="x")
    assert any("REF-" in t for t in ctx.bot.texts(55))


async def test_support_relay_roundtrip(ctx):
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, "support:msg")
    await say(ctx, BUYER, "سلام، سوال دارم")
    copied = [p for n, p in ctx.bot.calls if n == "CopyMessage"]
    assert copied and copied[0]["chat_id"] == ADMIN
    # ادمین روی پیام کپی‌شده (آیدی ۵۰۰) Reply می‌زند
    ctx.n += 1
    admin_u = User(id=ADMIN, is_bot=False, first_name="A")
    reply_to = Message(message_id=500, date=datetime.now(), chat=Chat(id=ADMIN, type="private"),
                       from_user=User(id=1, is_bot=True, first_name="B"), text="سلام، سوال دارم")
    msg = Message(message_id=ctx.n, date=datetime.now(), chat=Chat(id=ADMIN, type="private"),
                  from_user=admin_u, text="جواب شما", reply_to_message=reply_to)
    await ctx.dp.feed_update(ctx.bot, Update(update_id=ctx.n, message=msg))
    assert any("جواب شما" in t for t in ctx.bot.texts(BUYER))


async def test_force_sub_blocks_non_members_and_lets_members_in(ctx):
    pid = await _product(ctx)
    await ctx.db.set_setting("force_channel", "@mychan")

    ctx.bot.member_status = "left"
    await say(ctx, BUYER, "/start")
    assert any("عضو شو" in t for t in ctx.bot.texts(BUYER))
    await tap(ctx, BUYER, "fs:check")
    assert any("عضو نشده" in a for a in ctx.bot.alerts())
    await tap(ctx, BUYER, f"buy:{pid}")  # دور زدن قفل با کالبک ممکن نیست
    assert not any("روش پرداخت" in t for t in ctx.bot.texts(BUYER))

    ctx.bot.member_status = "member"
    await tap(ctx, BUYER, "fs:check")
    assert any("دوره را انتخاب کن" in t for t in ctx.bot.texts(BUYER))
    await say(ctx, ADMIN, "/start")  # ادمین هرگز قفل نمی‌شود
    ctx.bot.member_status = "left"
    await say(ctx, ADMIN, "/admin")
    assert any("پنل ادمین" in t for t in ctx.bot.texts(ADMIN))


async def test_throttle_drops_fast_repeats():
    t = {"now": 0.0}
    th = Throttle(1.0, clock=lambda: t["now"])
    calls = []

    async def handler(event, data):
        calls.append(1)

    u = User(id=5, is_bot=False, first_name="x")
    data = {"event_from_user": u, "settings": Settings(bot_token="x")}
    await th(handler, object(), data)
    await th(handler, object(), data)  # بلافاصله -> حذف
    t["now"] = 2.0
    await th(handler, object(), data)
    assert len(calls) == 2


async def test_admin_set_command_validates(ctx):
    await say(ctx, ADMIN, "/set referral_percent 150")
    assert any("۰ تا ۱۰۰" in t for t in ctx.bot.texts(ADMIN))
    await say(ctx, ADMIN, "/set referral_percent 25")
    assert await ctx.db.get_setting("referral_percent") == "25"
    await say(ctx, ADMIN, "/set force_channel @abc")
    assert await ctx.db.get_setting("force_channel") == "@abc"


async def test_cover_photo_card_and_sold_out_block(ctx):
    pid = await _product(ctx)
    await ctx.db.update_product(pid, "cover_file_id", "COVER")
    await ctx.db.update_product(pid, "seats", 1)
    await say(ctx, BUYER, "/start")
    await tap(ctx, BUYER, f"p:{pid}")
    assert any(n == "SendPhoto" and p["photo"] == "COVER" and "جای خالی" in p["caption"]
               for n, p in ctx.bot.calls)

    other = 55
    await ctx.db.upsert_user(other, None, "o")
    await ctx.db.mark_paid(await ctx.db.create_order(other, await ctx.db.get_product(pid), "card"))
    await tap(ctx, BUYER, f"buy:{pid}")
    assert any("تکمیل" in a for a in ctx.bot.alerts())
    assert not any("روش پرداخت" in t for t in ctx.bot.texts(BUYER))


async def test_rating_callback_flow(ctx):
    pid = await _product(ctx)
    await ctx.db.upsert_user(BUYER, None, "b")
    oid = await ctx.db.create_order(BUYER, await ctx.db.get_product(pid), "card")
    await ctx.db.mark_paid(oid)
    await tap(ctx, BUYER, f"rate:{oid}:2")
    assert any("پشتیبانی" in t for t in ctx.bot.texts(BUYER))  # امتیاز پایین، مسیر پیگیری
    await tap(ctx, BUYER, f"rate:{oid}:5")
    assert any("قبلاً امتیاز" in a for a in ctx.bot.alerts())
    await tap(ctx, 12345, f"rate:{oid}:5")  # سفارش دیگران
    assert (await ctx.db.get_product(pid))["rating_count"] == 1


async def test_sale_and_edit_commands(ctx):
    pid = await _product(ctx, 900_000)
    await say(ctx, ADMIN, f"/sale {pid} 1000000 24")
    assert (await ctx.db.get_product(pid))["on_sale"] == 0  # بالاتر از قیمت اصلی رد می‌شود
    await say(ctx, ADMIN, f"/sale {pid} 600000 24")
    assert (await ctx.db.get_product(pid))["price"] == 600_000
    await say(ctx, ADMIN, f"/sale {pid} off")
    assert (await ctx.db.get_product(pid))["price"] == 900_000

    await tap(ctx, ADMIN, f"adm:ed:seats:{pid}")
    await say(ctx, ADMIN, "۲۰")
    assert (await ctx.db.get_product(pid))["seats"] == 20
    await tap(ctx, ADMIN, f"adm:ed:features:{pid}")
    await say(ctx, ADMIN, "پروژه واقعی\nپشتیبانی ۳ ماهه")
    assert "پروژه واقعی" in (await ctx.db.get_product(pid))["features"]
    await tap(ctx, ADMIN, f"adm:p:{pid}")
    assert any("باقی" in t and "فروش" in t for t in ctx.bot.texts(ADMIN))
