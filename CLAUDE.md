# راهنمای مخزن (برای Claude Code)

ربات تلگرام فروش دوره: Python + aiogram 3 + SQLite، اجرا روی سرور شخصی با Docker (`docs/DEPLOY.md`).
نسخه‌ی سرورلس لغو شده و حذف شد.

## قواعد
- هر تغییر پرداخت/تحویل فقط از `bot/services/fulfillment.py::complete_order` عبور کند (اتمیک، تحویل یک‌بار).
- قیمت‌ها در دیتابیس **تومان**؛ فقط داخل `zarinpal.py` ×۱۰ به ریال تبدیل می‌شود.
- مهاجرت دیتابیس: یک ورودی جدید در `MIGRATIONS` (`bot/db.py`)؛ هرگز اسکیمای قبلی را دست نزن.
- متن‌های کاربر فقط در `bot/texts.py`. فارسی، لحن صمیمی و کوتاه.
- قبل از پوش: `ruff check . && python -m pytest -q --cov=bot` (آستانه‌ی پوشش ۸۸٪).
- `.env` و توکن هرگز commit نشود؛ تست `test_deploy` این را کنترل می‌کند.
- سیم‌کشی فقط در `bot/app.py::create_dispatcher`؛ تست‌ها هم از همان استفاده می‌کنند.

## اسکیل‌های نصب‌شده (`.claude/skills`, منبع: `SOURCES.md`)
- متن پیام‌ها و صفحه محصول → `copywriting`, `copy-editing`, `humanizer`
- قیمت/پیشنهاد/تخفیف → `pricing`, `offers`, `marketing-psychology`
- برنامه معرفی و یادآوری → `referrals`, `emails`, `onboarding`
- پاسخ به اعتراض مشتری → `sales-objections`, `sales-followup`
- تغییر در پرداخت/وب‌هوک/دسترسی → حتماً `security-audit`
