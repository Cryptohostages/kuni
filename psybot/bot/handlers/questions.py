from datetime import datetime, time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import admin_screens, screens, texts
from ..callbacks import Menu
from ..config import Settings
from ..db import Repo, User
from ..filters import TEXT
from ..notify import notify_admins
from ..states import Ask
from ..timeutil import Clock
from ..ui import Screen, show

router = Router(name="questions")

MIN_LENGTH = 3
MAX_LENGTH = 2000


async def blocked_screen(user: User, repo: Repo, clock: Clock, config: Settings) -> Screen | None:
    if user.is_banned:
        return screens.ask_banned()
    today = datetime.combine(clock.now().date(), time.min)
    sent = await repo.questions_since(user.id, today)
    if sent >= config.questions_per_day:
        return screens.ask_limit()
    return None


@router.message(Command("ask"))
@router.callback_query(Menu.filter(F.to == "ask"))
async def ask(event: Message | CallbackQuery, state: FSMContext, user: User, repo: Repo, clock: Clock,
              config: Settings) -> None:
    await state.clear()
    blocked = await blocked_screen(user, repo, clock, config)
    if blocked:
        await show(event, blocked)
        return
    await state.set_state(Ask.text)
    await show(event, screens.ask_prompt())


@router.message(Ask.text, TEXT)
async def got_question(message: Message, state: FSMContext, user: User, repo: Repo, clock: Clock,
                       config: Settings, bot: Bot) -> None:
    text = (message.text or "").strip()
    if len(text) < MIN_LENGTH:
        await message.answer("Напиши чуть подробнее, хотя бы пару слов.")
        return
    if len(text) > MAX_LENGTH:
        await message.answer(f"Получилось длинновато: можно до {MAX_LENGTH} символов. Сократи, пожалуйста.")
        return
    await state.clear()
    blocked = await blocked_screen(user, repo, clock, config)
    if blocked:
        await show(message, blocked)
        return
    question_id = await repo.add_question(user.id, text, clock.now())
    await show(message, screens.ask_sent())
    question = await repo.get_question(question_id)
    assert question is not None
    await notify_admins(bot, config, admin_screens.notify_question(question))


@router.message(Ask.text, ~F.text)
async def not_text(message: Message) -> None:
    await message.answer(texts.TEXT_ONLY)
