import { api } from 'sdk';
import { esc } from './util.js';
import { ADMIN_IDS } from './config.js';
import { getProduct, hasCodes, claimCode } from './store.js';

async function warnAdmins(order, reason) {
  for (const id of ADMIN_IDS) {
    try {
      await api.sendMessage({ chat_id: id, text: `⚠️ تحویل سفارش #${order.id} کامل نشد. ${reason}\nکاربر: ${order.userId}` });
    } catch (e) {
      console.error('admin notify failed', e);
    }
  }
}

// لینک یک‌بارمصرف کانال + کد لایسنس + متن ثابت
export async function deliver(order) {
  const p = await getProduct(order.productId);
  const parts = [`✅ دسترسی به دوره <b>${esc(p.title)}</b>:`];

  if (p.channelId) {
    try {
      const link = await api.createChatInviteLink({ chat_id: p.channelId, member_limit: 1, name: `order ${order.id}` });
      parts.push(`🔗 لینک ورود (یک‌بارمصرف):\n${link.invite_link}`);
    } catch (e) {
      console.error('invite link failed', e);
      parts.push('⚠️ ساخت لینک کانال با خطا روبه‌رو شد؛ پشتیبانی به‌زودی لینک را برایتان می‌فرستد.');
      await warnAdmins(order, 'ساخت لینک کانال ناموفق بود (ربات ادمین کانال است؟)');
    }
  }

  if (await hasCodes(p.id)) {
    const code = await claimCode(p.id, order.id);
    if (code) {
      parts.push(`🔑 کد دسترسی شما:\n<code>${esc(code)}</code>`);
    } else {
      parts.push('⚠️ کد شما در حال آماده‌سازی است و توسط پشتیبانی ارسال می‌شود.');
      await warnAdmins(order, 'کدهای دوره تمام شده است');
    }
  }

  if (p.accessText) parts.push(esc(p.accessText));
  if (parts.length === 1) parts.push('جزئیات دسترسی توسط پشتیبانی برایتان ارسال می‌شود.');

  await api.sendMessage({
    chat_id: order.userId,
    text: parts.join('\n\n'),
    parse_mode: 'HTML',
    link_preview_options: { is_disabled: true },
  });
}
