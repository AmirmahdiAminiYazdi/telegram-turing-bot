"""کلاینت زرین‌پال در برابر یک درگاه جعلی HTTP (بدون شبکه‌ی بیرونی)."""
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.services.zarinpal import Zarinpal, ZarinpalError


@pytest.fixture
async def gateway():
    calls: list[tuple[str, dict]] = []
    replies = {"request": {"data": {"code": 100, "authority": "A0001"}, "errors": []},
               "verify": {"data": {"code": 100, "ref_id": 777}, "errors": []}}

    async def handle(request: web.Request):
        name = request.match_info["name"]
        calls.append((name, await request.json()))
        return web.json_response(replies[name])

    app = web.Application()
    app.router.add_post("/pg/v4/payment/{name}.json", handle)
    server = TestServer(app)
    await server.start_server()
    z = Zarinpal("MERCHANT-ID")
    z.api = f"http://127.0.0.1:{server.port}/pg/v4/payment"
    yield z, calls, replies
    await server.close()


async def test_request_converts_toman_to_rial_and_returns_link(gateway):
    z, calls, _ = gateway
    authority, url = await z.request(150_000, "https://x.ir/pay/callback", "سفارش 1")
    assert authority == "A0001" and url.endswith("/pg/StartPay/A0001")
    name, payload = calls[0]
    assert name == "request"
    assert payload == {"merchant_id": "MERCHANT-ID", "amount": 1_500_000,
                       "callback_url": "https://x.ir/pay/callback", "description": "سفارش 1"}


async def test_request_failure_raises(gateway):
    z, _, replies = gateway
    replies["request"] = {"data": [], "errors": {"code": -9, "message": "invalid"}}
    with pytest.raises(ZarinpalError):
        await z.request(1000, "https://x.ir/cb", "d")


@pytest.mark.parametrize("code", [100, 101])
async def test_verify_success_codes(gateway, code):
    z, calls, replies = gateway
    replies["verify"] = {"data": {"code": code, "ref_id": 42}, "errors": []}
    assert await z.verify(2000, "A1") == "42"
    assert calls[-1][1] == {"merchant_id": "MERCHANT-ID", "amount": 20_000, "authority": "A1"}


async def test_verify_unpaid_returns_none(gateway):
    z, _, replies = gateway
    replies["verify"] = {"data": [], "errors": {"code": -53}}
    assert await z.verify(2000, "A1") is None


async def test_network_error_is_wrapped():
    z = Zarinpal("M")
    z.api = "http://127.0.0.1:1/pg/v4/payment"  # پورت بسته
    with pytest.raises(ZarinpalError):
        await z.verify(1000, "A")


def test_sandbox_hosts():
    assert "sandbox.zarinpal.com" in Zarinpal("M", sandbox=True).api
    assert "payment.zarinpal.com" in Zarinpal("M").api
