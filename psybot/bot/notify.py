import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import Settings
from .ui import Screen

log = logging.getLogger(__name__)


async def send(bot: Bot, chat_id: int, screen: Screen) -> bool:
    """Отправить сообщение, не падая, если человек остановил бота."""
    try:
        await bot.send_message(chat_id, screen.text, reply_markup=screen.markup)
    except TelegramAPIError as e:
        log.warning("Не удалось отправить сообщение %s: %s", chat_id, e)
        return False
    return True


async def notify_admins(bot: Bot, config: Settings, screen: Screen) -> None:
    for admin_id in config.admin_ids:
        await send(bot, admin_id, screen)
