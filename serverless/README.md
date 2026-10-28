# حالت سرورلس (Telegram Serverless)

همان ربات فروش دوره، ولی بدون سرور و روی زیرساخت خود تلگرام ([مستندات](https://core.telegram.org/bots/serverless)).
کد در `tgcloud/` است و با CLI رسمی `tgcloud` دیپلوی می‌شود. نسخه‌ی پایتون (aiogram) در ریشه‌ی مخزن برای اجرا روی VPS باقی می‌ماند.

> دیتابیس همین SQLite داخلی تلگرام است (نیازی به Postgres نیست). کلید خارجی ندارد و `schema.js` را با `tgcloud migrate` اعمال می‌کنیم.

## راه‌اندازی
1. در @BotFather: ربات → **Serverless** را روشن کن. از **CLI Access** توکن `app<id>:<secret>` را بگیر (غیر از توکن ربات).
2. آیدی عددی ادمین‌ها را در `tgcloud/lib/config.js` (`ADMIN_IDS`) بنویس (از @userinfobot).
3. دیپلوی:
   ```bash
   cd serverless
   npm install
   npx tgcloud login      # توکن CLI
   npx tgcloud push       # آپلود کد + صفحه‌ی بازگشت از درگاه
   npx tgcloud migrate    # ساخت جدول‌ها
   ```
4. تنظیمات از داخل ربات (به‌عنوان ادمین، `/set`):
   ```
   /set card_number 6037...
   /set card_holder نام صاحب کارت
   /set support_username my_support
   /set zarinpal_merchant xxxxxxxx-xxxx-...
   /set app_base https://app<id>.tgcloud.ai      # آدرسی که push چاپ می‌کند
   ```
   سپس `/admin` را بزن و محصولات را بساز. پیام `/set zarinpal_merchant …` را بعد از ارسال پاک کن.

## تفاوت با نسخه‌ی سرور
- **متغیر محیطی نیست:** کارت، مرچنت و … در جدول `settings` ذخیره می‌شوند. فقط `ADMIN_IDS` در کد است.
- **حافظه بین اجراها نمی‌ماند:** مرحله‌ی گفتگوی ادمین (`/admin` → محصول جدید) در جدول `states` است.
- **آدرس عمومی ندارد:** callback زرین‌پال روی صفحه‌ی ثابت `public/pay/` می‌نشیند (روی `app<id>.tgcloud.ai`)
  و کاربر را با `t.me/<bot>?start=v_<Authority>` به ربات برمی‌گرداند. ربات پرداخت را **مستقیم از زرین‌پال** تایید می‌کند و `Status` مرورگر را باور نمی‌کند. دکمه‌ی «بررسی پرداخت» هم هست.
- **پیام همگانی مرحله‌ای است:** هر بار ۲۵ نفر با دکمه‌ی «ارسال مرحله‌ی بعد» (محدودیت زمان اجرا و نرخ تلگرام).
- پرداخت آنلاین بدون `app_base` و مرچنت خاموش است و فقط کارت‌به‌کارت نشان داده می‌شود.

## بررسی بدون دیپلوی
```bash
npm run check                                         # سینتکس، importها و نبودن کلید خارجی + تست‌ها
npx tgcloud run handlers/message '{ chat:{id:1,type:"private"}, from:{id:1,first_name:"A"}, text:"/start" }'
```
