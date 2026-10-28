import { isAdmin } from '../lib/config.js';
import { onStart, onReceipt } from '../lib/user.js';
import { onMessage as onAdminMessage } from '../lib/admin.js';

export default async function (message) {
  if (message.chat.type !== 'private' || !message.from) return;
  const text = (message.text ?? '').trim();

  if (text === '/start' || text.startsWith('/start ')) {
    return onStart(message, text.slice(6).trim());
  }
  if (isAdmin(message.from.id) && (await onAdminMessage(message, text))) return;
  if (message.photo) return onReceipt(message);
}
