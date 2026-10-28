import { api, BotApiError } from 'sdk';
import { esc, fmt } from './util.js';
import { T } from './texts.js';
import * as kb from './kb.js';
import * as store from './store.js';
import { deliver } from './delivery.js';
import { requestPayment, verifyPayment } from './zarinpal.js';
import { ADMIN_IDS } from './config.js';

const HTML = 'HTML';

export async function send(chatId, text, markup) {
  return api.sendMessage({ chat_id: chatId, text, parse_mode: HTML, reply_markup: markup });
}

// ویرایش پیام کالبک؛ خطای «تغییری نکرد» بی‌ضرر است
export async function edit(cb, text, markup) {
  try {
    await api.editMessageText({
      chat_id: cb.message.chat.id, message_id: cb.message.message_id,
      text, parse_mode: HTML, reply_markup: markup,
    });
  } catch (e) {
    if (!(e instanceof BotApiError && e.code === 400)) throw e;
  }
}

export const ack = (cb, text, alert = false) =>
  api.answerCallbackQuery({ callback_query_id: cb.id, text, show_alert: alert });

async function methodsEnabled() {
  const [merchant, appBase, card] = await Promise.all([
    store.getSetting('zarinpal_merchant'), store.getSetting('app_base'), store.getSetting('card_number'),
  ]);
  return { zarinpal: Boolean(merchant && appBase), card: Boolean(card) };
}

async function botUsername() {
  let name = await store.getSetting('bot_username');
  if (!name) {
    name = (await api.getMe()).username;
    await store.setSetting('bot_username', name);
  }
  return name;
}

const productText = (p) => T.productCard(esc(p.title), esc(p.description), fmt(p.price));

async function showProduct(chatId, id) {
  const p = await store.getProduct(id);
  if (!p || !p.active) return send(chatId, T.noProducts);
  return send(chatId, productText(p), kb.product(p.id));
}

// ---- /start ----
export async function onStart(message, payload) {
  const u = message.from;
  const chatId = message.chat.id;
  const isVerify = payload.startsWith('v_');
  await store.upsertUser(u, payload && !isVerify ? payload : null);
  await store.clearState(u.id);

  if (isVerify) return verifyByAuthority(chatId, u.id, payload.slice(2));
  if (/^p_\d+$/.test(payload)) return showProduct(chatId, Number(payload.slice(2)));
  return send(chatId, T.welcome(esc(u.first_name ?? '')), kb.mainMenu());
}

// ---- پرداخت آنلاین ----
// تایید همیشه سرور-به-سرور با زرین‌پال است؛ پارامتر Status برگشتی از مرورگر به آن اعتماد نمی‌شود.
async function verifyOrder(order) {
  if (order.status === 'paid') return 'already';
  const merchant = await store.getSetting('zarinpal_merchant');
  const sandbox = (await store.getSetting('zarinpal_sandbox')) === 'true';
  const ref = await verifyPayment({ merchant, sandbox, amountToman: order.amount, authority: order.authority });
  if (ref === null) return 'unpaid';
  return (await store.markPaid(order.id, ref)) ? 'paid' : 'already';
}

async function settle(order, chatId) {
  const r = await verifyOrder(order);
  if (r === 'unpaid') return send(chatId, T.notPaidYet);
  if (r === 'paid') await send(chatId, T.paidOk);
  return deliver(order); // برای already هم دسترسی دوباره ارسال می‌شود (کد/لینک تکراری نمی‌سازد جز لینک جدید)
}

async function verifyByAuthority(chatId, userId, authority) {
  const order = await store.getOrderByAuthority(authority);
  if (!order || order.userId !== userId || order.method !== 'zarinpal') return send(chatId, T.notPaidYet);
  return settle(order, chatId);
}

// ---- کالبک‌ها ----
export async function onCallback(cb) {
  const d = cb.data ?? '';
  const uid = cb.from.id;
  const chatId = cb.message?.chat.id;
  if (!chatId) return true;

  if (d === 'menu') {
    await edit(cb, T.welcome(esc(cb.from.first_name ?? '')), kb.mainMenu());
  } else if (d === 'catalog') {
    const list = await store.listProducts();
    await (list.length ? edit(cb, T.catalog, kb.catalog(list)) : edit(cb, T.noProducts, kb.mainMenu()));
  } else if (d.startsWith('p:')) {
    const p = await store.getProduct(Number(d.slice(2)));
    if (!p || !p.active) return ack(cb, T.noProducts, true);
    await edit(cb, productText(p), kb.product(p.id));
  } else if (d.startsWith('buy:')) {
    const p = await store.getProduct(Number(d.slice(4)));
    if (!p || !p.active) return ack(cb, T.noProducts, true);
    const owned = await store.paidOrder(uid, p.id);
    if (owned) {
      await send(chatId, T.alreadyOwned);
      await deliver(owned);
      return ack(cb);
    }
    const m = await methodsEnabled();
    if (!m.zarinpal && !m.card) return ack(cb, T.noMethods, true);
    await edit(cb, `${productText(p)}\n\n${T.chooseMethod}`, kb.methods(p.id, m.zarinpal, m.card));
  } else if (d.startsWith('pz:')) {
    return payOnline(cb, uid, Number(d.slice(3)));
  } else if (d.startsWith('pc:')) {
    const card = await store.getSetting('card_number');
    const p = await store.getProduct(Number(d.slice(3)));
    if (!card) return ack(cb, T.noMethods, true);
    if (!p || !p.active) return ack(cb, T.noProducts, true);
    const order = await store.createOrder(uid, p, 'card');
    const holder = await store.getSetting('card_holder');
    await edit(cb, T.cardInfo(order.id, fmt(p.price), esc(card), holder ? `به نام ${esc(holder)}` : ''));
  } else if (d.startsWith('chk:')) {
    const order = await store.getOrder(Number(d.slice(4)));
    if (!order || order.userId !== uid || order.method !== 'zarinpal' || !order.authority) return ack(cb);
    await ack(cb);
    return settle(order, chatId);
  } else if (d === 'mine') {
    const list = await store.userPaidOrders(uid);
    await (list.length ? edit(cb, T.mine, kb.mine(list)) : edit(cb, T.mineEmpty, kb.mainMenu()));
  } else if (d.startsWith('again:')) {
    const order = await store.getOrder(Number(d.slice(6)));
    if (order && order.userId === uid && order.status === 'paid') await deliver(order);
  } else if (d === 'support') {
    const s = await store.getSetting('support_username');
    await edit(cb, s ? T.support(esc(s)) : T.supportNone, kb.mainMenu());
  } else {
    return false;
  }
  return ack(cb).then(() => true).catch(() => true);
}

async function payOnline(cb, uid, productId) {
  const p = await store.getProduct(productId);
  if (!p || !p.active) return ack(cb, T.noProducts, true);
  const [merchant, appBase, sandbox] = await Promise.all([
    store.getSetting('zarinpal_merchant'), store.getSetting('app_base'), store.getSetting('zarinpal_sandbox'),
  ]);
  if (!merchant || !appBase) return ack(cb, T.noMethods, true);

  const order = await store.createOrder(uid, p, 'zarinpal');
  const pay = await requestPayment({
    merchant, sandbox: sandbox === 'true', amountToman: p.price,
    callbackUrl: `${appBase.replace(/\/$/, '')}/pay/${await botUsername()}`,
    description: `سفارش ${order.id} - ${p.title}`,
  });
  if (!pay) return ack(cb, T.zarinpalFail, true);
  await store.setAuthority(order.id, pay.authority);
  await edit(cb, T.zarinpalPay(order.id), kb.payLink(pay.url, order.id));
  return ack(cb);
}

// ---- رسید کارت‌به‌کارت ----
export async function onReceipt(message) {
  const u = message.from;
  const order = await store.openCardOrder(u.id);
  if (!order) return send(message.chat.id, T.noActiveOrder);
  const fileId = message.photo[message.photo.length - 1].file_id;
  await store.setReceipt(order.id, fileId);
  await send(message.chat.id, T.receiptReceived);

  const p = await store.getProduct(order.productId);
  const caption =
    `🧾 رسید جدید\nسفارش #${order.id}\nدوره: ${esc(p.title)}\nمبلغ: ${fmt(order.amount)} تومان\n` +
    `کاربر: ${esc([u.first_name, u.last_name].filter(Boolean).join(' '))} (<code>${u.id}</code>)`;
  for (const adminId of ADMIN_IDS) {
    try {
      await api.sendPhoto({ chat_id: adminId, photo: fileId, caption, parse_mode: HTML, reply_markup: kb.receiptReview(order.id) });
    } catch (e) {
      console.error('admin notify failed', adminId, e);
    }
  }
}
