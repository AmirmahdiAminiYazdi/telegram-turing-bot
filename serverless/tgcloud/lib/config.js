// آیدی عددی ادمین‌ها (از @userinfobot). این‌ها محرمانه نیستند.
export const ADMIN_IDS = [];

// تعداد پیام هر مرحله‌ی ارسال همگانی (زیر سقف نرخ تلگرام و زمان اجرا)
export const BROADCAST_CHUNK = 25;

export const isAdmin = (id) => ADMIN_IDS.includes(id);
