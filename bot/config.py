import os
import re
from dataclasses import dataclass, field


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    # مجموعه‌ی قابل‌تغییر: /claim اولین ادمین را در زمان اجرا اضافه می‌کند
    admin_ids: set[int] | frozenset[int] = field(default_factory=set)
    db_path: str = "data/bot.sqlite3"
    support_username: str = ""
    card_number: str = ""
    card_holder: str = ""
    zarinpal_merchant_id: str = ""
    zarinpal_sandbox: bool = False
    public_base_url: str = ""
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    throttle_seconds: float = 0.4

    @property
    def zarinpal_enabled(self) -> bool:
        return bool(self.zarinpal_merchant_id and self.public_base_url)

    @property
    def card_enabled(self) -> bool:
        return bool(self.card_number)


def parse_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise RuntimeError(f"ADMIN_IDS شامل مقدار نامعتبر است: {part!r} (فقط آیدی عددی)")
        ids.add(int(part))
    return ids


TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است")
    if not TOKEN_RE.match(token):
        raise RuntimeError("BOT_TOKEN فرمت معتبر ندارد (باید مثل 123456:ABC… باشد)")
    admins = parse_ids(env.get("ADMIN_IDS", ""))
    return Settings(
        bot_token=token,
        admin_ids=admins,
        db_path=env.get("DB_PATH", "data/bot.sqlite3"),
        support_username=env.get("SUPPORT_USERNAME", "").lstrip("@"),
        card_number=env.get("CARD_NUMBER", "").strip(),
        card_holder=env.get("CARD_HOLDER", "").strip(),
        zarinpal_merchant_id=env.get("ZARINPAL_MERCHANT_ID", "").strip(),
        zarinpal_sandbox=_bool(env.get("ZARINPAL_SANDBOX", "false")),
        public_base_url=env.get("PUBLIC_BASE_URL", "").rstrip("/"),
        web_host=env.get("WEB_HOST", "0.0.0.0"),
        web_port=int(env.get("WEB_PORT", "8080")),
        throttle_seconds=float(env.get("THROTTLE_SECONDS", "0.4")),
    )
