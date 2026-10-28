from aiogram.types import CallbackQuery, Message

from bot.config import Settings


class IsAdmin:
    """فقط ادمین‌های تعریف‌شده در ADMIN_IDS."""

    def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user.id in settings.admin_ids
