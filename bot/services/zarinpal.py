from __future__ import annotations

import aiohttp

TOMAN_TO_RIAL = 10
OK_CODES = {100, 101}  # 101 = قبلا تایید شده


class ZarinpalError(Exception):
    pass


class Zarinpal:
    def __init__(self, merchant_id: str, sandbox: bool = False,
                 session: aiohttp.ClientSession | None = None):
        host = "sandbox.zarinpal.com" if sandbox else "payment.zarinpal.com"
        self.api = f"https://{host}/pg/v4/payment"
        self.start_url = f"https://{host}/pg/StartPay/"
        self.merchant_id = merchant_id
        self._session = session

    async def _post(self, path: str, payload: dict) -> dict:
        payload = {"merchant_id": self.merchant_id, **payload}
        session = self._session or aiohttp.ClientSession()
        try:
            async with session.post(
                f"{self.api}/{path}.json", json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ZarinpalError(f"network error: {exc}") from exc
        finally:
            if self._session is None:
                await session.close()
        return body

    async def request(self, amount_toman: int, callback_url: str,
                      description: str) -> tuple[str, str]:
        """(authority, پیوند پرداخت) را برمی‌گرداند."""
        body = await self._post("request", {
            "amount": amount_toman * TOMAN_TO_RIAL,
            "callback_url": callback_url,
            "description": description,
        })
        data = body.get("data") or {}
        if data.get("code") != 100 or not data.get("authority"):
            raise ZarinpalError(f"request failed: {body.get('errors') or body}")
        return data["authority"], self.start_url + data["authority"]

    async def verify(self, amount_toman: int, authority: str) -> str | None:
        """ref_id را در صورت موفقیت و None را در غیر این صورت برمی‌گرداند."""
        body = await self._post("verify", {
            "amount": amount_toman * TOMAN_TO_RIAL,
            "authority": authority,
        })
        data = body.get("data") or {}
        if data.get("code") in OK_CODES:
            return str(data.get("ref_id", ""))
        return None
