import { isAdmin } from '../lib/config.js';
import { onCallback } from '../lib/user.js';
import { onCallback as onAdminCallback } from '../lib/admin.js';

export default async function (cb) {
  if (!cb.message) return;
  if ((cb.data ?? '').startsWith('a:')) {
    if (isAdmin(cb.from.id)) await onAdminCallback(cb);
    return;
  }
  await onCallback(cb);
}
