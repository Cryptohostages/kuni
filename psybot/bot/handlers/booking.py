from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from .. import admin_screens, screens, texts
from ..callbacks import BookConfirm, BookDay, BookSlot, BookTopic, Menu
from ..config import Settings
from ..db import BookResult, Repo, Slot, User
from ..filters import TEXT
from ..notify import notify_admins
from ..states import Booking as BookingState
from ..states import Profile
from ..timeutil import Clock, parse_day_key
from ..ui import Screen, btn, kb, show

router = Router(name="booking")

COMMENT_LIMIT = 500
# записался-отменил по кругу — психологу каждый раз приходит уведомление, поэтому есть потолок
MAX_BOOKINGS_PER_DAY = 6


def not_before(now: datetime, config: Settings) -> datetime:
    return now + timedelta(minutes=config.min_lead_minutes)


def last_day(now: datetime, config: Settings) -> date:
    return now.date() + timedelta(days=config.booking_days_ahead)


async def days_screen(user: User, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    upcoming = await repo.upcoming_for_user(user.id, now)
    if len(upcoming) >= config.max_active_bookings:
        return screens.book_limit(len(upcoming))
    days = await repo.free_days(not_before(now, config), last_day(now, config))
    return screens.book_days(days, now.date())


async def free_slot(slot_id: int | None, repo: Repo, clock: Clock, config: Settings) -> Slot | None:
    """Окошко, если на него всё ещё можно записаться."""
    if not slot_id:
        return None
    slot = await repo.get_slot(slot_id)
    now = clock.now()
    if not slot or slot.starts_at.date() > last_day(now, config):
        return None
    free = await repo.free_slots(slot.starts_at.date(), not_before(now, config))
    return slot if any(s.id == slot.id for s in free) else None


async def day_screen(day: date | None, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    day = day or now.date()
    slots = []
    if day <= last_day(now, config):
        slots = await repo.free_slots(day, not_before(now, config))
    return screens.book_slots(day, slots, config)


@router.message(Command("book"))
@router.callback_query(Menu.filter(F.to == "book"))
async def start(event: Message | CallbackQuery, state: FSMContext, user: User, repo: Repo, clock: Clock,
                config: Settings) -> None:
    await state.clear()
    await show(event, await days_screen(user, repo, clock, config))


@router.callback_query(BookDay.filter())
async def pick_day(callback: CallbackQuery, callback_data: BookDay, repo: Repo, clock: Clock,
                   config: Settings) -> None:
    day = parse_day_key(callback_data.day)
    await show(callback, await day_screen(day, repo, clock, config))


@router.callback_query(BookSlot.filter())
async def pick_slot(callback: CallbackQuery, callback_data: BookSlot, callback_answer: CallbackAnswer,
                    state: FSMContext, repo: Repo, clock: Clock, config: Settings) -> None:
    slot = await free_slot(callback_data.id, repo, clock, config)
    if slot is None:
        callback_answer.text = "Это время уже заняли, выбери другое"
        taken = await repo.get_slot(callback_data.id)
        await show(callback, await day_screen(taken.starts_at.date() if taken else None, repo, clock, config))
        return
    await state.set_data({"slot_id": slot.id})
    await show(callback, screens.book_topic(slot, clock.now().date()))


@router.callback_query(BookTopic.filter())
async def pick_topic(callback: CallbackQuery, callback_data: BookTopic, callback_answer: CallbackAnswer,
                     state: FSMContext, user: User, repo: Repo, clock: Clock, config: Settings) -> None:
    slot = await free_slot(callback_data.slot, repo, clock, config)
    if slot is None:
        callback_answer.text = "Это время уже недоступно, выбери другое"
        await show(callback, await days_screen(user, repo, clock, config))
        return
    data = await state.get_data()
    if data.get("slot_id") != slot.id:
        # тему выбрали на старом экране: берём время, которое было на нём
        data = {"slot_id": slot.id}
    data["topic"] = callback_data.code
    await state.set_data(data)
    if not user.has_profile:
        await state.update_data(after="booking")
        await state.set_state(Profile.name)
        back = kb(btn("← Назад", BookConfirm(action="back", slot=slot.id)))
        await show(callback, Screen(texts.NAME_PROMPT, back))
        return
    await show(callback, screens.book_confirm(slot, user, callback_data.code, data.get("comment"), config))


async def confirm_screen(state: FSMContext, user: User, repo: Repo, clock: Clock, config: Settings) -> Screen | None:
    data = await state.get_data()
    slot = await free_slot(data.get("slot_id"), repo, clock, config)
    if slot is None or "topic" not in data or not user.has_profile:
        return None
    return screens.book_confirm(slot, user, data["topic"], data.get("comment"), config)


async def flow_slot(callback_data: BookConfirm, state: FSMContext, repo: Repo, clock: Clock,
                    config: Settings) -> Slot | None:
    """Окошко с кнопки, если это та же запись, что сейчас в процессе, и время ещё свободно."""
    data = await state.get_data()
    if data.get("slot_id") != callback_data.slot:
        return None
    return await free_slot(callback_data.slot, repo, clock, config)


@router.callback_query(BookConfirm.filter(F.action.in_({"skip", "clear", "back"})))
async def confirm_nav(callback: CallbackQuery, callback_data: BookConfirm, callback_answer: CallbackAnswer,
                      state: FSMContext, user: User, repo: Repo, clock: Clock, config: Settings) -> None:
    slot = await flow_slot(callback_data, state, repo, clock, config)
    if slot is None:
        callback_answer.text = "Это время уже недоступно, выбери другое"
        await show(callback, await days_screen(user, repo, clock, config))
        return
    if callback_data.action == "back":
        await show(callback, screens.book_topic(slot, clock.now().date()))
        return
    if callback_data.action == "clear":
        await state.update_data(comment=None)
    screen = await confirm_screen(state, user, repo, clock, config)
    await show(callback, screen or await days_screen(user, repo, clock, config))


@router.callback_query(BookConfirm.filter(F.action == "comment"))
async def ask_comment(callback: CallbackQuery, callback_data: BookConfirm, callback_answer: CallbackAnswer,
                      state: FSMContext, user: User, repo: Repo, clock: Clock, config: Settings) -> None:
    if await flow_slot(callback_data, state, repo, clock, config) is None:
        callback_answer.text = "Это время уже недоступно, выбери другое"
        await show(callback, await days_screen(user, repo, clock, config))
        return
    data = await state.get_data()
    await state.set_state(BookingState.comment)
    await show(callback, screens.comment_prompt(callback_data.slot, bool(data.get("comment"))))


@router.message(BookingState.comment, TEXT)
async def got_comment(message: Message, state: FSMContext, user: User, repo: Repo, clock: Clock,
                      config: Settings) -> None:
    comment = (message.text or "").strip()
    if len(comment) > COMMENT_LIMIT:
        await message.answer(f"Получилось {len(comment)} символов, а можно до {COMMENT_LIMIT}. Сократи, пожалуйста.")
        return
    await state.set_state(None)
    await state.update_data(comment=comment or None)
    screen = await confirm_screen(state, user, repo, clock, config)
    if screen is None:
        await message.answer("Увы, это время уже заняли. Выбери другое.")
        screen = await days_screen(user, repo, clock, config)
    await show(message, screen)


@router.message(BookingState.comment, ~F.text)
async def comment_not_text(message: Message) -> None:
    await message.answer(texts.TEXT_ONLY)


@router.callback_query(BookConfirm.filter(F.action == "ok"))
async def confirm(callback: CallbackQuery, callback_data: BookConfirm, callback_answer: CallbackAnswer,
                  state: FSMContext, user: User, repo: Repo, clock: Clock, config: Settings, bot: Bot) -> None:
    data = await state.get_data()
    if data.get("slot_id") != callback_data.slot or "topic" not in data or not user.has_profile:
        # повторное нажатие после записи или кнопка со старого экрана
        mine = await repo.active_booking(user.id, callback_data.slot)
        if mine:
            await show(callback, screens.booked(mine, config))
            return
        callback_answer.text = texts.STALE
        await show(callback, await days_screen(user, repo, clock, config))
        return

    now = clock.now()
    result, booking_id = await repo.create_booking(
        user_id=user.id,
        slot_id=callback_data.slot,
        topic=data.get("topic"),
        comment=data.get("comment"),
        now=now,
        not_before=not_before(now, config),
        not_after=last_day(now, config),
        max_active=config.max_active_bookings,
        max_per_day=MAX_BOOKINGS_PER_DAY,
    )
    if result is BookResult.TOO_OFTEN:
        await state.clear()
        await show(callback, screens.book_too_often())
        return
    if result is BookResult.LIMIT:
        await state.clear()
        await show(callback, await days_screen(user, repo, clock, config))
        return
    if result in (BookResult.TAKEN, BookResult.UNAVAILABLE) or booking_id is None:
        if result is BookResult.TAKEN:
            callback_answer.text = "Это время только что заняли. Выбери другое"
        else:
            callback_answer.text = "На это время записаться уже нельзя. Выбери другое"
        callback_answer.show_alert = True
        slot = await repo.get_slot(callback_data.slot)
        await show(callback, await day_screen(slot.starts_at.date() if slot else None, repo, clock, config))
        return

    await state.clear()
    booking = await repo.get_booking(booking_id)
    assert booking is not None
    await show(callback, screens.booked(booking, config))
    if result is BookResult.OK:
        await notify_admins(bot, config, admin_screens.notify_booked(booking, now.date()))
