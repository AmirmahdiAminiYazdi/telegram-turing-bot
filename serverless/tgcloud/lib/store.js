import { db } from 'sdk';
import { eq, and, or, desc, asc, gt, inArray, isNull } from 'sdk/db';
import { users, products, codes, orders, settings, states, broadcasts } from '../schema.js';

// ---- تنظیمات ----
export async function getSetting(key) {
  const row = await db.select().from(settings).where(eq(settings.key, key)).get();
  return row ? row.value : '';
}

export async function setSetting(key, value) {
  await db.insert(settings).values({ key, value })
    .onConflictDoUpdate({ target: settings.key, set: { value } }).run();
}

// ---- مرحله‌ی گفتگو ----
export async function getState(userId) {
  return (await db.select().from(states).where(eq(states.userId, userId)).get()) ?? null;
}

export async function setState(userId, step, data = {}) {
  await db.insert(states).values({ userId, step, data })
    .onConflictDoUpdate({ target: states.userId, set: { step, data } }).run();
}

export async function clearState(userId) {
  await db.delete(states).where(eq(states.userId, userId)).run();
}

// ---- کاربران ----
export async function upsertUser(u, source) {
  await db.insert(users)
    .values({ id: u.id, username: u.username ?? null, fullName: [u.first_name, u.last_name].filter(Boolean).join(' '), source: source ?? null })
    .onConflictDoUpdate({
      target: users.id,
      set: { username: u.username ?? null, fullName: [u.first_name, u.last_name].filter(Boolean).join(' ') },
    }).run();
}

// ---- محصولات ----
export const getProduct = (id) => db.select().from(products).where(eq(products.id, id)).get();

export const listProducts = (onlyActive = true) =>
  onlyActive
    ? db.select().from(products).where(eq(products.active, 1)).orderBy(asc(products.id)).all()
    : db.select().from(products).orderBy(asc(products.id)).all();

export async function addProduct(p) {
  const [row] = await db.insert(products).values(p).returning().run();
  return row;
}

export async function toggleProduct(id) {
  await db.run('UPDATE products SET active = 1 - active WHERE id = :id', { ':id': id });
}

// محصولی که سفارش دارد حذف نمی‌شود (کلید خارجی نداریم، پس خودمان چک می‌کنیم)
export async function deleteProduct(id) {
  if ((await db.$count(orders, eq(orders.productId, id))) > 0) return false;
  await db.delete(codes).where(eq(codes.productId, id)).run();
  await db.delete(products).where(eq(products.id, id)).run();
  return true;
}

// ---- کدهای لایسنس ----
export async function addCodes(productId, list) {
  for (let i = 0; i < list.length; i += 100) {
    await db.insert(codes).values(list.slice(i, i + 100).map((code) => ({ productId, code }))).run();
  }
  return list.length;
}

export const freeCodes = (productId) =>
  db.$count(codes, and(eq(codes.productId, productId), isNull(codes.orderId)));

export const hasCodes = async (productId) => (await db.$count(codes, eq(codes.productId, productId))) > 0;

// یک کد آزاد را اتمیک به سفارش می‌دهد؛ اگر قبلاً گرفته همان را برمی‌گرداند
export async function claimCode(productId, orderId) {
  const mine = await db.select().from(codes).where(eq(codes.orderId, orderId)).get();
  if (mine) return mine.code;
  for (let i = 0; i < 5; i++) {
    const free = await db.select().from(codes)
      .where(and(eq(codes.productId, productId), isNull(codes.orderId)))
      .orderBy(asc(codes.id)).limit(1).get();
    if (!free) return null;
    const r = await db.run('UPDATE codes SET order_id = :o WHERE id = :id AND order_id IS NULL',
      { ':o': orderId, ':id': free.id });
    if (r.rowsAffected === 1) return free.code;
  }
  return null;
}

// ---- سفارش‌ها ----
export async function createOrder(userId, product, method) {
  const [row] = await db.insert(orders)
    .values({ userId, productId: product.id, amount: product.price, method }).returning().run();
  return row;
}

export const getOrder = (id) => db.select().from(orders).where(eq(orders.id, id)).get();
export const getOrderByAuthority = (a) => db.select().from(orders).where(eq(orders.authority, a)).get();

export async function setAuthority(id, authority) {
  await db.update(orders).set({ authority }).where(eq(orders.id, id)).run();
}

export async function setReceipt(id, fileId) {
  const r = await db.run(
    "UPDATE orders SET receipt_file_id = :f, status = 'receipt_sent' WHERE id = :id AND method = 'card' AND status IN ('pending','receipt_sent')",
    { ':f': fileId, ':id': id });
  return r.rowsAffected === 1;
}

// فقط اولین تبدیل به paid موفق می‌شود؛ جلوی تحویل دوباره را می‌گیرد
export async function markPaid(id, refId = null) {
  const r = await db.run(
    "UPDATE orders SET status = 'paid', ref_id = COALESCE(:ref, ref_id), paid_at = unixepoch() WHERE id = :id AND status != 'paid'",
    { ':ref': refId, ':id': id });
  return r.rowsAffected === 1;
}

export async function rejectOrder(id) {
  const r = await db.run("UPDATE orders SET status = 'rejected' WHERE id = :id AND status = 'receipt_sent'", { ':id': id });
  return r.rowsAffected === 1;
}

export const paidOrder = (userId, productId) =>
  db.select().from(orders)
    .where(and(eq(orders.userId, userId), eq(orders.productId, productId), eq(orders.status, 'paid')))
    .orderBy(desc(orders.id)).limit(1).get();

export const openCardOrder = (userId) =>
  db.select().from(orders)
    .where(and(eq(orders.userId, userId), eq(orders.method, 'card'), inArray(orders.status, ['pending', 'receipt_sent'])))
    .orderBy(desc(orders.id)).limit(1).get();

export async function userPaidOrders(userId) {
  const list = await db.select().from(orders)
    .where(and(eq(orders.userId, userId), eq(orders.status, 'paid'))).orderBy(desc(orders.id)).all();
  const out = [];
  for (const o of list) out.push({ ...o, title: (await getProduct(o.productId))?.title ?? '—' });
  return out;
}

export const pendingReceipts = () =>
  db.select().from(orders).where(eq(orders.status, 'receipt_sent')).orderBy(asc(orders.id)).all();

export async function stats() {
  const paidRow = await db.get("SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS s FROM orders WHERE status = 'paid'");
  return {
    users: await db.$count(users),
    orders: await db.$count(orders),
    paid: paidRow.n,
    revenue: paidRow.s,
  };
}

// ---- پیام همگانی (مرحله‌ای، بدون نیاز به کار پس‌زمینه) ----
export async function createBroadcast(text) {
  const [row] = await db.insert(broadcasts).values({ text }).returning().run();
  return row;
}
export const getBroadcast = (id) => db.select().from(broadcasts).where(eq(broadcasts.id, id)).get();

export const nextUsers = (afterId, limit) =>
  db.select().from(users).where(gt(users.id, afterId)).orderBy(asc(users.id)).limit(limit).all();

export async function progressBroadcast(id, lastUserId, ok, fail, done) {
  await db.run(
    'UPDATE broadcasts SET last_user_id = :l, ok = ok + :ok, fail = fail + :f, done = :d WHERE id = :id',
    { ':l': lastUserId, ':ok': ok, ':f': fail, ':d': done ? 1 : 0, ':id': id });
}
