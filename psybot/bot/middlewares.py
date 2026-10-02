from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser

from .db import Repo
from .timeutil import Clock


class UserMiddleware(BaseMiddleware):
    """Заводит пользователя в базе при первом сообщении и кладёт его в data["user"]."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        chat = data.get("event_chat")
        if chat is not None and chat.type != "private":
            # бот рассчитан только на личные сообщения
            return None
        repo: Repo = data["repo"]
        clock: Clock = data["clock"]
        data["user"] = await repo.touch_user(tg_user.id, tg_user.username, tg_user.full_name, clock.now())
        return await handler(event, data)
