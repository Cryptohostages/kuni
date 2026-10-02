"""Окошки: недельный обзор и редактор дня."""

from datetime import date, datetime, timedelta

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens
from ...callbacks import AdmDay, AdmSlot, AdmWeek
from ...config import Settings
from ...db import Repo
from ...filters import TEXT
from ...states import AdminInput
from ...timeutil import Clock, day_key, grid_times, hm, is_work_day, parse_day_key
from ...ui import Screen, show
from ...validators import parse_time

router = Router(name="admin_slots")


def max_week(config: Settings) -> int:
    return (config.admin_days_ahead - 1) // 7


def week_of(day: date, today: date) -> int:
    return max(0, (day - today).days // 7)


async def week_screen(week_no: int, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    today = now.date()
    first = today + timedelta(days=7 * week_no)
    days = [first + timedelta(days=i) for i in range(7)]
    overview = await repo.days_overview(days[0], days[-1], now)
    return admin_screens.week(week_no, days, overview, set(config.work_days), today, max_week(config))


async def day_screen(day: date, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    items = await repo.day_slots(day)
    grid = grid_times(config) if is_work_day(day, config) or items else []
    return admin_screens.day_editor(day, items, grid, now, week_of(day, now.date()))


def in_range(day: date, today: date, config: Settings) -> bool:
    return today <= day <= today + timedelta(days=config.admin_days_ahead)


@router.callback_query(AdmWeek.filter())
async def week(callback: CallbackQuery, callback_data: AdmWeek, state: FSMContext, repo: Repo, clock: Clock,
               config: Settings) -> None:
    await state.clear()
    week_no = min(max(callback_data.week, 0), max_week(config))
    await show(callback, await week_screen(week_no, repo, clock, config))


@router.callback_query(AdmDay.filter())
async def day_action(callback: CallbackQuery, callback_data: AdmDay, callback_answer: CallbackAnswer,
                     state: FSMContext, repo: Repo, clock: Clock, config: Settings) -> None:
    await state.clear()
    now = clock.now()
    day = parse_day_key(callback_data.day)
    if not in_range(day, now.date(), config):
        callback_answer.text = "Этот день уже недоступен"
        await show(callback, await week_screen(0, repo, clock, config))
        return

    if callback_data.action == "custom":
        await state.set_state(AdminInput.custom_time)
        await state.set_data({"day": callback_data.day})
        await show(callback, admin_screens.custom_time_prompt(day))
        return

    if callback_data.action == "open_all":
        existing = {item.slot.starts_at for item in await repo.day_slots(day)}
        for t in grid_times(config):
            starts = datetime.combine(day, t)
            if starts >= now and starts not in existing:
                await repo.put_slot(starts, config.slot_minutes, is_open=True)
        await repo.set_day_free_slots(day, now, is_open=True)
        callback_answer.text = "Всё время на этот день открыто"
    elif callback_data.action == "close_free":
        await repo.set_day_free_slots(day, now, is_open=False)
        callback_answer.text = "Свободное время закрыто, записи остались"

    await show(callback, await day_screen(day, repo, clock, config))


@router.callback_query(AdmSlot.filter())
async def toggle_slot(callback: CallbackQuery, callback_data: AdmSlot, callback_answer: CallbackAnswer,
                      repo: Repo, clock: Clock, config: Settings) -> None:
    now = clock.now()
    day = parse_day_key(callback_data.day)
    starts = datetime.strptime(f"{callback_data.day}{callback_data.hm}", "%Y%m%d%H%M")

    booked = next(
        (item.booking for item in await repo.day_slots(day) if item.slot.starts_at == starts and item.booking),
        None,
    )
    if booked:
        await show(callback, admin_screens.booking(booked, now, f"d{day_key(day)}"))
        return
    if starts < now:
        callback_answer.text = "Это время уже прошло"
        await show(callback, await day_screen(day, repo, clock, config))
        return

    slot = await repo.get_slot_at(starts)
    if slot and slot.is_open:
        if await repo.close_slot_if_free(slot.id):
            callback_answer.text = f"{hm(starts)} закрыто"
        else:
            callback_answer.text = "На это время только что записались"
    else:
        await repo.put_slot(starts, config.slot_minutes, is_open=True)
        callback_answer.text = f"{hm(starts)} открыто"
    await show(callback, await day_screen(day, repo, clock, config))


@router.message(AdminInput.custom_time, TEXT)
async def got_custom_time(message: Message, state: FSMContext, repo: Repo, clock: Clock, config: Settings) -> None:
    data = await state.get_data()
    day = parse_day_key(data["day"])
    t = parse_time(message.text or "")
    if t is None:
        await message.answer("Не понял время. Напиши, например, <i>15:30</i>.")
        return
    starts = datetime.combine(day, t)
    if starts < clock.now():
        await message.answer("Это время уже прошло. Напиши другое.")
        return
    await state.clear()
    await repo.put_slot(starts, config.slot_minutes, is_open=True)
    await message.answer(f"Окошко на {hm(t)} открыто.")
    await show(message, await day_screen(day, repo, clock, config))
