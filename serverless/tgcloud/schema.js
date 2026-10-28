import { table, integer, text, sql, index, uniqueIndex } from 'sdk/db';

// توجه: روی Telegram Serverless کلید خارجی (foreign key) پشتیبانی نمی‌شود؛
// ارتباط‌ها با ستون ساده نگه داشته شده و یکپارچگی در کد رعایت می‌شود.

export const users = table('users', {
  id: integer('id').primaryKey(), // آیدی تلگرام
  username: text('username'),
  fullName: text('full_name'),
  source: text('source'), // مقدار ?start= هنگام اولین ورود
  createdAt: integer('created_at').notNull().default(sql`(unixepoch())`),
});

export const products = table('products', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  title: text('title').notNull(),
  description: text('description').notNull().default(''),
  price: integer('price').notNull(), // تومان
  channelId: integer('channel_id'), // کانال/گروه خصوصی برای لینک یک‌بارمصرف
  accessText: text('access_text'), // متن/لینک/کد دسترسی ثابت
  active: integer('active').notNull().default(1),
});

export const codes = table('codes', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  productId: integer('product_id').notNull(),
  code: text('code').notNull(),
  orderId: integer('order_id'),
}, (t) => ({
  byProduct: index('idx_codes_product').on(t.productId),
  byOrder: index('idx_codes_order').on(t.orderId),
}));

// status: pending -> receipt_sent (فقط کارت) -> paid | rejected
export const orders = table('orders', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  userId: integer('user_id').notNull(),
  productId: integer('product_id').notNull(),
  amount: integer('amount').notNull(), // تومان
  method: text('method').notNull(), // zarinpal | card
  status: text('status').notNull().default('pending'),
  authority: text('authority'),
  refId: text('ref_id'),
  receiptFileId: text('receipt_file_id'),
  createdAt: integer('created_at').notNull().default(sql`(unixepoch())`),
  paidAt: integer('paid_at'),
}, (t) => ({
  byUser: index('idx_orders_user').on(t.userId),
  byAuthority: uniqueIndex('uidx_orders_authority').on(t.authority),
}));

// تنظیمات قابل‌تغییر از داخل ربات (/set): کارت، مرچنت زرین‌پال، آدرس اپ و ...
export const settings = table('settings', {
  key: text('key').primaryKey(),
  value: text('value').notNull(),
});

// جایگزین FSM: مرحله‌ی گفتگوی ادمین (روی سرورلس حافظه بین اجراها نمی‌ماند)
export const states = table('states', {
  userId: integer('user_id').primaryKey(),
  step: text('step').notNull(),
  data: text('data', { mode: 'json' }),
});

export const broadcasts = table('broadcasts', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  text: text('text').notNull(),
  lastUserId: integer('last_user_id').notNull().default(0),
  ok: integer('ok').notNull().default(0),
  fail: integer('fail').notNull().default(0),
  done: integer('done').notNull().default(0),
});
