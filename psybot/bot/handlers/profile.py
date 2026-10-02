from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import screens, texts
from ..callbacks import BookConfirm, Menu
from ..config import Settings
from ..db import Repo, User
from ..filters import TEXT
from ..states import Profile
from ..timeutil import Clock
from ..ui import Screen, btn, kb, show
from ..validators import normalize_class, normalize_name
from .booking import confirm_screen, days_screen

router = Router(name="profile")


def back_kb(data: dict, user: User) -> InlineKeyboardMarkup:
    """«Назад» возвращает туда, откуда пришли, ничего не теряя."""
    if data.get("after") == "booking":
        action = "skip" if user.has_profile else "back"
        return kb(btn("← Назад", BookConfirm(action=action, slot=data["slot_id"])))
    return kb(btn("← Назад", Menu(to="my")))


@router.callback_query(Menu.filter(F.to == "profile"))
async def start(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    # из подтверждения записи возвращаемся к записи, из «Моих записей» — туда же
    data["after"] = "booking" if data.get("slot_id") and "topic" in data else "my"
    await state.set_data(data)
    await state.set_state(Profile.name)
    await show(callback, Screen(texts.NAME_PROMPT, back_kb(data, user)))


@router.message(Profile.name, TEXT)
async def got_name(message: Message, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    name = normalize_name(message.text or "")
    if name is None:
        await message.answer(texts.NAME_INVALID, reply_markup=back_kb(data, user))
        return
    await state.update_data(full_name=name)
    await state.set_state(Profile.class_name)
    await message.answer(texts.CLASS_PROMPT, reply_markup=back_kb(data, user))


@router.message(Profile.class_name, TEXT)
async def got_class(message: Message, state: FSMContext, user: User, repo: Repo, clock: Clock,
                    config: Settings) -> None:
    data = await state.get_data()
    class_name = normalize_class(message.text or "")
    if class_name is None:
        await message.answer(texts.CLASS_INVALID, reply_markup=back_kb(data, user))
        return
    await repo.set_profile(user.id, data["full_name"], class_name)
    await state.set_state(None)
    user = await repo.get_user(user.id) or user

    if data.get("after") == "booking":
        screen = await confirm_screen(state, user, repo, clock, config)
        if screen is None:
            await message.answer("Увы, пока мы знакомились, это время заняли. Выбери другое.")
            screen = await days_screen(user, repo, clock, config)
        await show(message, screen)
        return

    await state.clear()
    now = clock.now()
    bookings = await repo.upcoming_for_user(user.id, now)
    await show(message, screens.my_bookings(bookings, user, now.date(), config))


@router.message(Profile.name, ~F.text)
@router.message(Profile.class_name, ~F.text)
async def not_text(message: Message) -> None:
    await message.answer(texts.TEXT_ONLY)
