import { fetch } from 'sdk';

const TOMAN_TO_RIAL = 10;
const OK = [100, 101]; // 101 = قبلاً تایید شده

const hosts = (sandbox) => (sandbox ? 'sandbox.zarinpal.com' : 'payment.zarinpal.com');

async function post(sandbox, path, payload) {
  const res = await fetch(`https://${hosts(sandbox)}/pg/v4/payment/${path}.json`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: fetch.body.json(payload),
  });
  try {
    return await res.json();
  } catch {
    return {};
  }
}

// -> { authority, url } یا null
export async function requestPayment({ merchant, sandbox, amountToman, callbackUrl, description }) {
  const body = await post(sandbox, 'request', {
    merchant_id: merchant,
    amount: amountToman * TOMAN_TO_RIAL,
    callback_url: callbackUrl,
    description,
  });
  const data = body.data;
  if (!data || data.code !== 100 || !data.authority) {
    console.error('zarinpal request failed', JSON.stringify(body.errors ?? body));
    return null;
  }
  return { authority: data.authority, url: `https://${hosts(sandbox)}/pg/StartPay/${data.authority}` };
}

// -> refId (رشته) در صورت موفقیت، وگرنه null
export async function verifyPayment({ merchant, sandbox, amountToman, authority }) {
  const body = await post(sandbox, 'verify', {
    merchant_id: merchant,
    amount: amountToman * TOMAN_TO_RIAL,
    authority,
  });
  const data = body.data;
  return data && OK.includes(data.code) ? String(data.ref_id ?? '') : null;
}
