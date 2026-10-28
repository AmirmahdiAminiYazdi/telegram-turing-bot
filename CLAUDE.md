# راهنمای مخزن (برای Claude Code)

ربات تلگرام فروش دوره. دو پیاده‌سازی با قابلیت‌های هم‌راستا:
- `bot/` — Python + aiogram 3 + SQLite (اصلی، کامل‌ترین و تست‌شده؛ برای VPS/Docker)
- `serverless/` — JS روی Telegram Serverless (هنوز بدون کد تخفیف/معرفی/یادآوری/قفل عضویت/پشتیبانی)

## قواعد
- هر تغییر پرداخت/تحویل فقط از `bot/services/fulfillment.py::complete_order` عبور کند (اتمیک، تحویل یک‌بار).
- قیمت‌ها در دیتابیس **تومان**؛ فقط داخل `zarinpal.py` ×۱۰ به ریال تبدیل می‌شود.
- مهاجرت دیتابیس: یک ورودی جدید در `MIGRATIONS` (`bot/db.py`)؛ هرگز اسکیمای قبلی را دست نزن.
- متن‌های کاربر فقط در `bot/texts.py`. فارسی، لحن صمیمی و کوتاه.
- قبل از پوش: `python -m pytest -q`.

## اسکیل‌های نصب‌شده (`.claude/skills`, منبع: `SOURCES.md`)
- متن پیام‌ها و صفحه محصول → `copywriting`, `copy-editing`, `humanizer`
- قیمت/پیشنهاد/تخفیف → `pricing`, `offers`, `marketing-psychology`
- برنامه معرفی و یادآوری → `referrals`, `emails`, `onboarding`
- پاسخ به اعتراض مشتری → `sales-objections`, `sales-followup`
- تغییر در پرداخت/وب‌هوک/دسترسی → حتماً `security-audit`
