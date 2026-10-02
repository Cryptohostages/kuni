from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser

from .. import screens
from ..callbacks import Menu
from ..config import Settings
from ..db import Repo, User
from ..timeutil import Clock
from ..ui import Screen, show

router = Router(name="common")


async def home_screen(user: User, tg_user: TgUser, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    upcoming = await repo.upcoming_for_user(user.id, now)
    return screens.home(
        tg_user.first_name,
        upcoming[0] if upcoming else None,
        now.date(),
        config,
        config.is_admin(user.id),
    )


@router.message(CommandStart())
@router.callback_query(Menu.filter(F.to == "home"))
async def home(
    event: Message | CallbackQuery,
    state: FSMContext,
    user: User,
    event_from_user: TgUser,
    repo: Repo,
    clock: Clock,
    config: Settings,
) -> None:
    await state.clear()
    await show(event, await home_screen(user, event_from_user, repo, clock, config))


@router.message(Command("about"))
@router.callback_query(Menu.filter(F.to == "about"))
async def about(event: Message | CallbackQuery, state: FSMContext, config: Settings) -> None:
    await state.clear()
    await show(event, screens.about(config))


@router.message(Command("help"))
@router.callback_query(Menu.filter(F.to == "help"))
async def sos(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(event, screens.sos())
