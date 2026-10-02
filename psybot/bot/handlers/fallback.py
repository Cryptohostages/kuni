from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from aiogram.utils.callback_answer import CallbackAnswer

from .. import texts
from ..callbacks import Admin
from ..config import Settings
from ..db import Repo, User
from ..timeutil import Clock
from ..ui import btn, kb
from .common import home_screen

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, user: User, event_from_user: TgUser, repo: Repo, clock: Clock,
                          config: Settings) -> None:
    if config.is_admin(user.id):
        await message.answer(texts.UNKNOWN_ADMIN, reply_markup=kb(btn("🔑 Кабинет психолога", Admin(to="home"))))
        return
    screen = await home_screen(user, event_from_user, repo, clock, config)
    await message.answer(texts.UNKNOWN, reply_markup=screen.markup)


@router.callback_query()
async def stale_button(callback: CallbackQuery, callback_answer: CallbackAnswer) -> None:
    callback_answer.text = texts.STALE
    callback_answer.show_alert = True
