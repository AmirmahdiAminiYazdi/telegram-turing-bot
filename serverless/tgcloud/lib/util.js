const FA = '۰۱۲۳۴۵۶۷۸۹';
const AR = '٠١٢٣٤٥٦٧٨٩';

export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function fmt(n) {
  return Number(n).toLocaleString('en-US');
}

// "۱٬۲۰۰" یا "1,200" -> 1200 ؛ نامعتبر -> null
export function parsePrice(raw) {
  const s = String(raw)
    .replace(/[۰-۹]/g, (d) => FA.indexOf(d))
    .replace(/[٠-٩]/g, (d) => AR.indexOf(d))
    .replace(/[,٬،\s]/g, '');
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  return n > 0 && Number.isSafeInteger(n) ? n : null;
}

export function btn(text, data) {
  return { text, callback_data: data };
}

export const rows = (...r) => ({ inline_keyboard: r });
