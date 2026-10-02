import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import ErrorEvent
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from .config import Settings
from .db import Repo
from .handlers import admin, booking, common, fallback, my_bookings, profile, questions
from .middlewares import ERROR_TEXT, ButtonMiddleware, UserMiddleware
from .timeutil import Clock

log = logging.getLogger(__name__)


def create_bot(config: Settings) -> Bot:
    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else None
    return Bot(
        config.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def create_dispatcher(config: Settings, repo: Repo, clock: Clock, storage: BaseStorage | None = None) -> Dispatcher:
    # события одного человека обрабатываются по очереди: двойное нажатие не запишет дважды
    dp = Dispatcher(
        storage=storage, events_isolation=SimpleEventIsolation(), config=config, repo=repo, clock=clock
    )
    dp.update.outer_middleware(UserMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.callback_query.middleware(ButtonMiddleware())
    # порядок важен: кабинет психолога раньше общих обработчиков, «не понял» — последним
    dp.include_routers(
        admin.router,
        common.router,
        booking.router,
        my_bookings.router,
        questions.router,
        profile.router,
        fallback.router,
    )
    dp.errors.register(on_error)
    return dp


async def on_error(event: ErrorEvent) -> bool:
    log.exception("Ошибка при обработке update %s", event.update.update_id, exc_info=event.exception)
    # на нажатия кнопок ButtonMiddleware уже показал всплывашку
    if event.update.message:
        try:
            await event.update.message.answer(ERROR_TEXT)
        except TelegramAPIError:
            pass
    return True
