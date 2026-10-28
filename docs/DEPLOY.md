# راهنمای استقرار روی سرور شخصی

## پیش‌نیاز
- سرور اوبونتو 22.04+ یا دبیان 12 با دسترسی root/sudo (۱ هسته و ۱ گیگ رم کافی است)
- اتصال سرور به `api.telegram.org` (برای سرورهای داخل ایران ممکن است پروکسی/تونل لازم باشد)
- برای **پرداخت آنلاین**: دامنه‌ای که A رکوردش به IP سرور اشاره کند و پورت‌های ۸۰ و ۴۴۳ باز باشد
- بدون دامنه هم کار می‌کند؛ فقط کارت‌به‌کارت فعال می‌ماند

## نصب (۵ دقیقه)
```bash
git clone <آدرس مخزن> /opt/telegram-turing-bot && cd /opt/telegram-turing-bot
git checkout claude/telegram-sales-bot-design-qfmj4k      # یا شاخه‌ی اصلی بعد از merge
sudo ./deploy/install.sh --firewall
```
اسکریپت Docker را نصب می‌کند، توکن و تنظیمات را می‌پرسد (توکن نمایش داده نمی‌شود)، `.env` را با دسترسی ۶۰۰ می‌سازد
و ربات، پشتیبان‌گیر و (اگر دامنه دادی) Caddy با HTTPS خودکار را بالا می‌آورد. بعد از سالم شدن، پیام شروع را چاپ می‌کند.

حالت غیرتعاملی (CI/Ansible):
```bash
export BOT_TOKEN=... ADMIN_IDS=123,456 DOMAIN=bot.example.com
sudo -E ./deploy/install.sh --yes --firewall
```
اگر `.env` از قبل دارید (مثلاً از سیستم خودتان): `scp .env server:/opt/telegram-turing-bot/.env && chmod 600 .env` و سپس `make up` یا `make up-https`.

## اولین ادمین
- اگر `ADMIN_IDS` را خالی گذاشتی، در لاگ استارت (`make logs`) خطی مثل `/claim Ab12…` چاپ می‌شود.
  آن را در تلگرام برای ربات بفرست؛ فرستنده ادمین می‌شود و `/claim` از آن لحظه برای همیشه غیرفعال است.
  بعد از ۵ حدس غلط، ۱۰ دقیقه قفل می‌شود.
- یا آیدی عددی را از @userinfobot بگیر و در `ADMIN_IDS` بگذار.

## بعد از نصب
1. `/admin` → «محصول جدید» (یا `python -m bot.tools.import_products courses.json` داخل کانتینر: `docker compose exec bot python -m bot.tools.import_products /tmp/c.json`).
2. ربات را **ادمین کانال/گروه خصوصی هر دوره** کنید (دسترسی دعوت کاربر و برای استرداد، مسدود کردن).
3. پرداخت آنلاین: `ZARINPAL_MERCHANT_ID` و `DOMAIN` را در `.env` بگذار، `make up-https`، و `https://DOMAIN/health` را باز کن؛ باید `{"ok": true}` بدهد.
   اول با `ZARINPAL_SANDBOX=true` یک خرید آزمایشی انجام بده.
4. یک خرید آزمایشی با کد تخفیف ۱۰۰٪ بساز تا مسیر تحویل را ببینی.

## عملیات روزمره
| کار | دستور |
|---|---|
| لاگ زنده | `make logs` |
| وضعیت سرویس‌ها | `make ps` |
| آپدیت (پشتیبان + pull + build) | `make update` |
| پشتیبان فوری | `make backup` |
| توقف | `make down` |

پشتیبان خودکار هر ۲۴ ساعت (۱۴ نسخه) در volume با نام `*_bot-backups` ذخیره می‌شود. **یک کپی بیرون از سرور** هم نگه دار:
```bash
docker run --rm -v telegram-turing-bot_bot-backups:/b -v "$PWD":/out alpine sh -c 'cp /b/bot-*.sqlite3 /out/ 2>/dev/null; ls /out'
```

### بازیابی
```bash
docker compose stop bot
docker run --rm -v telegram-turing-bot_bot-data:/data -v telegram-turing-bot_bot-backups:/b alpine \
  sh -c 'cp /b/bot-XXXX.sqlite3 /data/bot.sqlite3'
docker compose start bot
```

## امنیت
- `.env` فقط روی سرور با دسترسی ۶۰۰ است و وارد ایمیج نمی‌شود (`.dockerignore`). **هرگز آن را commit نکنید.**
- اگر توکن جایی لو رفت (چت، اسکرین‌شات، لاگ): BotFather → `/revoke` → توکن جدید در `.env` → `docker compose up -d`.
- کانتینر بدون root، فایل‌سیستم فقط‌خواندنی، بدون capability و با سقف حافظه اجرا می‌شود.
- از اینترنت فقط `/pay/callback` و `/health` در دسترس است؛ بقیه‌ی مسیرها ۴۰۴ می‌دهند.
- پرداخت‌ها همیشه سرور-به-سرور با زرین‌پال تایید می‌شوند؛ پارامتر `Status` مرورگر باور نمی‌شود.

## عیب‌یابی
| نشانه | علت/راه‌حل |
|---|---|
| «اتصال به تلگرام ناموفق بود» | توکن غلط، یا سرور به `api.telegram.org` دسترسی ندارد (فایروال/تحریم). `curl -I https://api.telegram.org` را تست کن |
| ربات بالا می‌آید ولی جواب نمی‌دهد | ربات دیگری با همان توکن در حال polling است (خطای Conflict). نمونه‌ی دیگر را خاموش کن |
| لینک کانال ساخته نمی‌شود | ربات ادمین کانال نیست یا آیدی کانال غلط است (باید `-100…` باشد) |
| پرداخت آنلاین برنمی‌گردد | `PUBLIC_BASE_URL` باید HTTPS و عمومی باشد؛ `https://DOMAIN/health` را از بیرون تست کن |
| قفل عضویت کار نمی‌کند | ربات باید در کانال ادمین باشد؛ وگرنه برای ادامه‌ی فروش نادیده گرفته می‌شود |
| سرویس `unhealthy` | `make logs`؛ معمولاً مجوز نوشتن روی volume یا خطای پیکربندی |
