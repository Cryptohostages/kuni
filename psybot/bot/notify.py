import logging
from enum import Enum

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from .config import Settings
from .ui import Screen

log = logging.getLogger(__name__)


class Delivery(Enum):
    OK = "ok"
    GONE = "gone"  # человек остановил бота: повторять бессмысленно
    FAILED = "failed"  # Telegram не принял сообщение
    RETRY = "retry"  # сеть или Telegram недоступны, можно попробовать позже


async def send(bot: Bot, chat_id: int, screen: Screen) -> Delivery:
    """Отправить сообщение, не падая. В лог не пишем, кому: это может быть автор анонимного вопроса."""
    try:
        await bot.send_message(chat_id, screen.text, reply_markup=screen.markup)
    except TelegramForbiddenError:
        return Delivery.GONE
    except (TelegramNetworkError, TelegramServerError, TelegramRetryAfter) as e:
        # текст ошибки флуд-контроля содержит номер чата, поэтому пишем только тип
        log.warning("Telegram недоступен (%s), сообщение не ушло", type(e).__name__)
        return Delivery.RETRY
    except TelegramAPIError as e:
        log.warning("Telegram не принял сообщение: %s", e.message)
        return Delivery.FAILED
    return Delivery.OK


async def notify_admins(bot: Bot, config: Settings, screen: Screen) -> list[Delivery]:
    return [await send(bot, admin_id, screen) for admin_id in config.admin_ids]
