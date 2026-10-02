from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from .. import admin_screens, screens, texts
from ..callbacks import Menu, MyBooking
from ..config import Settings
from ..db import Repo, Status, User
from ..notify import notify_admins
from ..timeutil import Clock
from ..ui import show

router = Router(name="my_bookings")


async def show_list(event: Message | CallbackQuery, user: User, repo: Repo, clock: Clock, config: Settings) -> None:
    now = clock.now()
    bookings = await repo.upcoming_for_user(user.id, now)
    await show(event, screens.my_bookings(bookings, user, now.date(), config))


@router.message(Command("my"))
@router.callback_query(Menu.filter(F.to == "my"))
async def my_list(event: Message | CallbackQuery, state: FSMContext, user: User, repo: Repo, clock: Clock,
                  config: Settings) -> None:
    await state.clear()
    await show_list(event, user, repo, clock, config)


@router.callback_query(MyBooking.filter())
async def my_booking(callback: CallbackQuery, callback_data: MyBooking, callback_answer: CallbackAnswer,
                     user: User, repo: Repo, clock: Clock, config: Settings, bot: Bot) -> None:
    booking = await repo.get_booking(callback_data.id)
    if booking is None or booking.user.id != user.id:
        callback_answer.text = texts.STALE
        return
    now = clock.now()

    if callback_data.action == "keep":
        callback_answer.text = "Отлично, до встречи!"
        try:
            await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        except TelegramBadRequest:
            pass
        return

    if booking.status != Status.ACTIVE or booking.starts_at <= now:
        callback_answer.text = "Эта запись уже неактуальна"
        await show_list(callback, user, repo, clock, config)
        return

    if callback_data.action == "view":
        await show(callback, screens.my_booking(booking, config))
    elif callback_data.action == "cancel":
        await show(callback, screens.my_cancel_confirm(booking, now.date()))
    elif callback_data.action == "cancel_yes":
        if await repo.cancel_booking(booking.id, by_admin=False, reason=None, now=now):
            await notify_admins(bot, config, admin_screens.notify_cancelled(booking, now.date()))
        await show(callback, screens.my_cancelled())
