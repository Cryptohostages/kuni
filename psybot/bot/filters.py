from aiogram import F
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from .config import Settings

# обычный текст, не команда: команды в любом состоянии уходят своим обработчикам
TEXT = F.text & ~F.text.startswith("/")


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery, config: Settings) -> bool:
        return event.from_user is not None and config.is_admin(event.from_user.id)
