import pytest

from bot.handlers import admin, admin_more, setup, user
from tests.helpers import make_ctx


@pytest.fixture(autouse=True)
def _detach_routers():
    """روترها singleton ماژول‌اند؛ برای ساخت Dispatcher تازه در هر تست جدا می‌شوند."""
    for r in (setup.router, admin.router, admin_more.router, user.router):
        r._parent_router = None
    yield


@pytest.fixture(autouse=True)
def _reset_user_middlewares():
    yield
    user.router.message.middleware._middlewares.clear()
    user.router.callback_query.middleware._middlewares.clear()


@pytest.fixture
async def ctx():
    c = await make_ctx()
    yield c
    await c.db.close()
