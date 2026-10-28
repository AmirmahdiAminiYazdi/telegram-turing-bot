import { btn, rows, fmt } from './util.js';

export const mainMenu = () =>
  rows([btn('📚 دوره‌ها', 'catalog')], [btn('🎒 دوره‌های من', 'mine'), btn('💬 پشتیبانی', 'support')]);

export const catalog = (products) =>
  rows(
    ...products.map((p) => [btn(`${p.title} — ${fmt(p.price)} ت`, `p:${p.id}`)]),
    [btn('⬅️ منو', 'menu')],
  );

export const product = (id) => rows([btn('🛒 خرید', `buy:${id}`)], [btn('⬅️ دوره‌ها', 'catalog')]);

export function methods(id, zarinpal, card) {
  const r = [];
  if (zarinpal) r.push([btn('💳 پرداخت آنلاین', `pz:${id}`)]);
  if (card) r.push([btn('🏦 کارت‌به‌کارت', `pc:${id}`)]);
  r.push([btn('⬅️ برگشت', `p:${id}`)]);
  return rows(...r);
}

export const payLink = (url, orderId) =>
  rows([{ text: '💳 رفتن به درگاه', url }], [btn('🔄 بررسی پرداخت', `chk:${orderId}`)]);

export const mine = (orders) =>
  rows(...orders.map((o) => [btn(`🔑 ${o.title}`, `again:${o.id}`)]), [btn('⬅️ منو', 'menu')]);

export const receiptReview = (id) => rows([btn('✅ تایید', `a:ok:${id}`), btn('❌ رد', `a:no:${id}`)]);

export const adminMenu = () =>
  rows(
    [btn('📦 محصولات', 'a:products'), btn('➕ محصول جدید', 'a:new')],
    [btn('🧾 رسیدهای منتظر', 'a:pending'), btn('📊 آمار', 'a:stats')],
    [btn('📣 پیام همگانی', 'a:bc')],
  );

export const adminProduct = (p) =>
  rows(
    [btn(p.active ? '🔴 غیرفعال کن' : '🟢 فعال کن', `a:tog:${p.id}`), btn('🗑 حذف', `a:del:${p.id}`)],
    [btn('🔑 افزودن کد لایسنس', `a:codes:${p.id}`)],
    [btn('⬅️ برگشت', 'a:products')],
  );

export const adminProducts = (products) =>
  rows(
    ...products.map((p) => [btn(`${p.active ? '🟢' : '🔴'} ${p.title} (${fmt(p.price)})`, `a:p:${p.id}`)]),
    [btn('⬅️ پنل', 'a:menu')],
  );

export const broadcastNext = (id) => rows([btn('▶️ ارسال مرحله‌ی بعد', `a:bcn:${id}`)]);
