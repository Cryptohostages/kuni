"""Главный экран психолога, списки записей и карточка записи."""

from datetime import date, datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens, screens
from ...callbacks import Admin, AdmBooking, AdmRecords
from ...db import Repo, Status
from ...filters import TEXT
from ...notify import Delivery, send
from ...states import AdminInput
from ...timeutil import Clock
from ...ui import Screen, show

router = Router(name="admin_panel")

MEETINGS = (Status.ACTIVE, Status.DONE, Status.MISSED)
REASON_LIMIT = 500


def day_bounds(first: date, days: int = 1) -> tuple[datetime, datetime]:
    start = datetime.combine(first, time.min)
    return start, start + timedelta(days=days)


@router.message(Command("admin"))
@router.callback_query(Admin.filter(F.to == "home"))
async def panel(event: Message | CallbackQuery, state: FSMContext, repo: Repo, clock: Clock) -> None:
    await state.clear()
    now = clock.now()
    today = await repo.bookings_between(*day_bounds(now.date()), MEETINGS)
    new_questions = await repo.new_questions()
    await show(event, admin_screens.panel(now.date(), today, now, len(new_questions)))


async def records_screen(span: str, repo: Repo, clock: Clock) -> Screen:
    today = clock.now().date()
    if span == "tomorrow":
        bounds = day_bounds(today + timedelta(days=1))
    elif span == "week":
        bounds = day_bounds(today, days=7)
    else:
        span, bounds = "today", day_bounds(today)
    bookings = await repo.bookings_between(*bounds, MEETINGS)
    return admin_screens.records(span, bookings, today)


@router.callback_query(AdmRecords.filter())
async def records(callback: CallbackQuery, callback_data: AdmRecords, state: FSMContext, repo: Repo,
                  clock: Clock) -> None:
    await state.clear()
    await show(callback, await records_screen(callback_data.span, repo, clock))


@router.callback_query(AdmBooking.filter())
async def booking_action(callback: CallbackQuery, callback_data: AdmBooking, callback_answer: CallbackAnswer,
                         state: FSMContext, repo: Repo, clock: Clock, bot: Bot) -> None:
    booking = await repo.get_booking(callback_data.id)
    if booking is None:
        callback_answer.text = "Запись не найдена"
        return
    now = clock.now()
    action, back = callback_data.action, callback_data.back
    started = booking.starts_at <= now

    if action == "cancel" and booking.status == Status.ACTIVE and not started:
        await state.set_state(AdminInput.cancel_reason)
        await state.set_data({"booking_id": booking.id, "back": back})
        await show(callback, admin_screens.cancel_reason_prompt(booking, now.date(), back))
        return

    await state.clear()
    if action == "no_reason":
        callback_answer.text = await cancel(booking.id, None, repo, clock, bot)
        callback_answer.show_alert = True
    elif action in ("done", "missed") and started:
        status = Status.DONE if action == "done" else Status.MISSED
        if booking.status != status and await repo.set_status(booking.id, status):
            callback_answer.text = "Отмечено"

    booking = await repo.get_booking(booking.id)
    assert booking is not None
    await show(callback, admin_screens.booking(booking, now, back))


@router.message(AdminInput.cancel_reason, TEXT)
async def got_cancel_reason(message: Message, state: FSMContext, repo: Repo, clock: Clock, bot: Bot) -> None:
    data = await state.get_data()
    reason = (message.text or "").strip()
    if len(reason) > REASON_LIMIT:
        await message.answer(f"Получилось {len(reason)} символов, а можно до {REASON_LIMIT}. Сократите, пожалуйста.")
        return
    await state.clear()
    note = await cancel(data["booking_id"], reason, repo, clock, bot)
    booking = await repo.get_booking(data["booking_id"])
    assert booking is not None
    await message.answer(note)
    await show(message, admin_screens.booking(booking, clock.now(), data.get("back", "today")))


@router.message(AdminInput.cancel_reason, ~F.text)
@router.message(AdminInput.answer, ~F.text)
@router.message(AdminInput.custom_time, ~F.text)
async def not_text(message: Message) -> None:
    await message.answer("Сюда нужен текст. Или нажмите кнопку под сообщением выше.")


async def cancel(booking_id: int, reason: str | None, repo: Repo, clock: Clock, bot: Bot) -> str:
    now = clock.now()
    booking = await repo.get_booking(booking_id)
    if booking is None or booking.starts_at <= now:
        return "Эту запись уже нельзя отменить"
    if not await repo.cancel_booking(booking_id, by_admin=True, reason=reason, now=now):
        return "Запись уже отменена"
    delivery = await send(bot, booking.user.id, screens.cancelled_by_admin(booking, reason, now.date()))
    if delivery is Delivery.OK:
        return "Запись отменена, ученик получил уведомление. Это время закрыто для записи"
    if delivery is Delivery.GONE:
        return "Запись отменена, но уведомление не дошло: ученик остановил бота"
    return "Запись отменена, но уведомление не дошло: Telegram не ответил. Лучше предупредить ученика лично"
