from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from aiogram.utils.callback_answer import CallbackAnswer

from .db import Repo
from .timeutil import Clock

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

ERROR_TEXT = "Что-то пошло не так. Можно попробовать ещё раз или начать сначала: /start"


class UserMiddleware(BaseMiddleware):
    """Заводит пользователя в базе при первом сообщении и кладёт его в data["user"].
    Всё, что приходит не из личного чата, бот молча пропускает."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat = data.get("event_chat")
        if chat is not None and chat.type != "private":
            return None
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return None
        repo: Repo = data["repo"]
        clock: Clock = data["clock"]
        data["user"] = await repo.touch_user(tg_user.id, tg_user.username, tg_user.full_name, clock.now())
        return await handler(event, data)


class ButtonMiddleware(BaseMiddleware):
    """Любое нажатие кнопки прерывает ввод текста: иначе, нажав кнопку под напоминанием посреди
    анонимного вопроса, человек отправил бы следующую фразу психологу. Данные (выбранное время,
    тема) при этом сохраняются. Если обработчик упал, человек увидит это во всплывашке."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        state: FSMContext | None = data.get("state")
        if state is not None:
            await state.set_state(None)
        try:
            return await handler(event, data)
        except Exception:
            answer: CallbackAnswer | None = data.get("callback_answer")
            if answer is not None and not answer.answered:
                answer.text, answer.show_alert = ERROR_TEXT, True
            raise
