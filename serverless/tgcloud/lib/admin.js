import { api } from 'sdk';
import { esc, fmt, parsePrice } from './util.js';
import { T } from './texts.js';
import * as kb from './kb.js';
import * as store from './store.js';
import { deliver } from './delivery.js';
import { send, edit, ack } from './user.js';
import { BROADCAST_CHUNK } from './config.js';

const SETTABLE = ['card_number', 'card_holder', 'zarinpal_merchant', 'zarinpal_sandbox', 'app_base', 'support_username'];
const SECRET = ['zarinpal_merchant'];

const productText = async (p) =>
  `<b>${esc(p.title)}</b>\nقیمت: ${fmt(p.price)} تومان\nکانال: ${p.channelId ?? '—'}\n` +
  `کد آزاد: ${await store.freeCodes(p.id)}\nوضعیت: ${p.active ? 'فعال' : 'غیرفعال'}`;

async function showProduct(cb, id) {
  const p = await store.getProduct(id);
  if (!p) return ack(cb, 'پیدا نشد', true);
  await edit(cb, await productText(p), kb.adminProduct(p));
}

// ---- پیام‌های ادمین؛ true یعنی مصرف شد ----
export async function onMessage(message, text) {
  const uid = message.from.id;
  const chatId = message.chat.id;

  if (text === '/admin') {
    await store.clearState(uid);
    await send(chatId, 'پنل ادمین', kb.adminMenu());
    return true;
  }
  if (text === '/cancel') {
    await store.clearState(uid);
    await send(chatId, T.canceled, kb.adminMenu());
    return true;
  }
  if (text.startsWith('/set')) return setCommand(chatId, text);

  const st = await store.getState(uid);
  if (!st || !text) return false;
  const data = st.data ?? {};

  switch (st.step) {
    case 'np_title':
      await store.setState(uid, 'np_desc', { title: text });
      await send(chatId, 'توضیحات دوره؟');
      return true;
    case 'np_desc':
      await store.setState(uid, 'np_price', { ...data, description: text });
      await send(chatId, 'قیمت به تومان؟ (فقط عدد)');
      return true;
    case 'np_price': {
      const price = parsePrice(text);
      if (!price) return send(chatId, 'عدد معتبر نیست؛ دوباره بفرست.').then(() => true);
      await store.setState(uid, 'np_channel', { ...data, price });
      await send(chatId, 'آیدی عددی کانال/گروه خصوصی دوره (مثل <code>-1001234567890</code>)؟\nربات باید ادمین آن باشد. اگر ندارد، <code>-</code> بفرست.');
      return true;
    }
    case 'np_channel': {
      let channelId = null;
      if (text !== '-') {
        channelId = Number(text);
        if (!Number.isSafeInteger(channelId)) return send(chatId, 'آیدی عددی نیست؛ دوباره بفرست یا - بزن.').then(() => true);
      }
      await store.setState(uid, 'np_access', { ...data, channelId });
      await send(chatId, 'متن/لینک دسترسی ثابت که بعد از خرید فرستاده شود؟ (یا -)');
      return true;
    }
    case 'np_access': {
      const p = await store.addProduct({
        title: data.title, description: data.description, price: data.price,
        channelId: data.channelId, accessText: text === '-' ? null : text,
      });
      await store.clearState(uid);
      await send(chatId, `✅ دوره #${p.id} ساخته شد.`, kb.adminMenu());
      return true;
    }
    case 'codes': {
      const list = text.split('\n').map((s) => s.trim()).filter(Boolean);
      const n = await store.addCodes(data.productId, list);
      await store.clearState(uid);
      await send(chatId, `✅ ${n} کد اضافه شد.`, kb.adminMenu());
      return true;
    }
    case 'bc': {
      await store.clearState(uid);
      const b = await store.createBroadcast(text);
      await send(chatId, `پیام همگانی ذخیره شد. برای ارسال، مرحله‌ها را با دکمه پیش ببر (هر مرحله ${BROADCAST_CHUNK} نفر).`, kb.broadcastNext(b.id));
      return true;
    }
    default:
      return false;
  }
}

// /set <key> <value>  (پیام بلافاصله پاک می‌شود چون ممکن است مرچنت داشته باشد)
async function setCommand(chatId, text) {
  const [, key, ...rest] = text.split(/\s+/);
  const value = rest.join(' ').trim();
  if (!SETTABLE.includes(key)) {
    await send(chatId, `کلیدهای مجاز:\n${SETTABLE.map((k) => `<code>/set ${k} مقدار</code>`).join('\n')}\n\nبرای پاک کردن مقدار، <code>-</code> بفرست.`);
    return true;
  }
  await store.setSetting(key, value === '-' ? '' : value);
  await send(chatId, `✅ ${key} ${SECRET.includes(key) ? 'ذخیره شد (مقدار نمایش داده نمی‌شود)' : `= ${esc(value)}`}`);
  return true;
}

// ---- کالبک‌ها: همه با پیشوند a: ----
export async function onCallback(cb) {
  const d = cb.data ?? '';
  if (!d.startsWith('a:')) return false;
  const uid = cb.from.id;
  const parts = d.split(':');
  const act = parts[1];
  const id = Number(parts[2]);

  switch (act) {
    case 'menu':
      await edit(cb, 'پنل ادمین', kb.adminMenu());
      break;
    case 'products': {
      const list = await store.listProducts(false);
      await edit(cb, list.length ? 'محصولات:' : 'محصولی ثبت نشده است.', kb.adminProducts(list));
      break;
    }
    case 'p':
      await showProduct(cb, id);
      break;
    case 'tog':
      await store.toggleProduct(id);
      await showProduct(cb, id);
      break;
    case 'del': {
      if (!(await store.deleteProduct(id))) return ack(cb, 'این محصول سفارش دارد؛ به‌جای حذف، غیرفعالش کن.', true);
      await edit(cb, 'حذف شد.', kb.adminProducts(await store.listProducts(false)));
      break;
    }
    case 'new':
      await store.setState(uid, 'np_title');
      await send(cb.message.chat.id, 'عنوان دوره؟ (/cancel برای انصراف)');
      break;
    case 'codes':
      await store.setState(uid, 'codes', { productId: id });
      await send(cb.message.chat.id, 'کدها را بفرست، هر کد در یک خط. (/cancel برای انصراف)');
      break;
    case 'pending': {
      const list = await store.pendingReceipts();
      if (!list.length) return ack(cb, 'رسید منتظری نیست', true);
      for (const o of list) {
        const p = await store.getProduct(o.productId);
        await api.sendPhoto({
          chat_id: cb.message.chat.id, photo: o.receiptFileId, parse_mode: 'HTML',
          caption: `سفارش #${o.id} — ${esc(p?.title ?? '')} — ${fmt(o.amount)} تومان`,
          reply_markup: kb.receiptReview(o.id),
        });
      }
      break;
    }
    case 'ok': {
      const order = await store.getOrder(id);
      if (!order || !(await store.markPaid(order.id))) return ack(cb, 'قبلا بررسی شده است', true);
      await send(order.userId, T.paidOk);
      await deliver(order);
      await markCaption(cb, '✅ تایید شد');
      break;
    }
    case 'no': {
      const order = await store.getOrder(id);
      if (!order || !(await store.rejectOrder(order.id))) return ack(cb, 'قبلا بررسی شده است', true);
      await send(order.userId, T.rejected(order.id));
      await markCaption(cb, '❌ رد شد');
      break;
    }
    case 'stats': {
      const s = await store.stats();
      const rate = s.orders ? `${Math.round((s.paid / s.orders) * 100)}%` : '—';
      await edit(cb,
        `👥 کاربران: ${s.users}\n🛒 سفارش‌ها: ${s.orders}\n✅ پرداخت‌شده: ${s.paid} (نرخ تبدیل ${rate})\n💰 درآمد: ${fmt(s.revenue)} تومان`,
        kb.adminMenu());
      break;
    }
    case 'bc':
      await store.setState(uid, 'bc');
      await send(cb.message.chat.id, 'متن پیام همگانی را بفرست. (/cancel برای انصراف)');
      break;
    case 'bcn':
      return broadcastStep(cb, id);
    default:
      return false;
  }
  await ack(cb).catch(() => {});
  return true;
}

async function markCaption(cb, suffix) {
  await api.editMessageCaption({
    chat_id: cb.message.chat.id, message_id: cb.message.message_id,
    caption: `${cb.message.caption ?? ''}\n\n${suffix}`,
  }).catch(() => {});
}

// هر بار یک دسته را می‌فرستد و مکان را ذخیره می‌کند؛ نیازی به پردازش پس‌زمینه نیست.
async function broadcastStep(cb, id) {
  const b = await store.getBroadcast(id);
  if (!b || b.done) return ack(cb, 'این ارسال تمام شده است', true);
  const batch = await store.nextUsers(b.lastUserId, BROADCAST_CHUNK);
  let ok = 0;
  let fail = 0;
  for (const u of batch) {
    try {
      await api.sendMessage({ chat_id: u.id, text: b.text });
      ok++;
    } catch {
      fail++;
    }
  }
  const done = batch.length < BROADCAST_CHUNK;
  const last = batch.length ? batch[batch.length - 1].id : b.lastUserId;
  await store.progressBroadcast(id, last, ok, fail, done);
  const total = { ok: b.ok + ok, fail: b.fail + fail };
  await edit(cb,
    `${done ? '✅ ارسال تمام شد' : '⏳ در حال ارسال'}\nموفق: ${total.ok} | ناموفق: ${total.fail}`,
    done ? kb.adminMenu() : kb.broadcastNext(id));
  return ack(cb).then(() => true);
}
