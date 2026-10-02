"""Окошки: недельный обзор и редактор дня."""

from datetime import date, datetime, timedelta

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens
from ...callbacks import AdmDay, AdmSlot, AdmWeek
from ...config import Settings
from ...db import DaySlot, Repo, find_clash
from ...filters import TEXT
from ...states import AdminInput
from ...timeutil import Clock, day_key, grid_times, hm, is_work_day, parse_day_key, time_range
from ...ui import Screen, show
from ...validators import parse_time

router = Router(name="admin_slots")


def max_week(config: Settings) -> int:
    return config.admin_days_ahead // 7


def week_of(day: date, today: date) -> int:
    return max(0, (day - today).days // 7)


def in_range(day: date, today: date, config: Settings) -> bool:
    return today <= day <= today + timedelta(days=config.admin_days_ahead)


def clash_text(item: DaySlot) -> str:
    return f"Пересекается с {time_range(item.slot.starts_at, item.slot.minutes)}. Сначала закройте его"


async def week_screen(week_no: int, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    today = now.date()
    last = today + timedelta(days=config.admin_days_ahead)
    first = today + timedelta(days=7 * week_no)
    days = [d for d in (first + timedelta(days=i) for i in range(7)) if d <= last]
    overview = await repo.days_overview(days[0], days[-1], now)
    return admin_screens.week(week_no, days, overview, set(config.work_days), today, max_week(config))


async def day_screen(day: date, repo: Repo, clock: Clock, config: Settings) -> Screen:
    now = clock.now()
    items = await repo.day_slots(day)
    grid = grid_times(config) if is_work_day(day, config) else []
    return admin_screens.day_editor(day, items, grid, now, week_of(day, now.date()))


def on_grid(starts: datetime, config: Settings) -> bool:
    """Время из сетки настроек: такие окошки бот ведёт сам, остальные — открытые вручную."""
    return config.auto_open and is_work_day(starts.date(), config) and starts.time() in grid_times(config)


async def open_all(day: date, repo: Repo, now: datetime, config: Settings) -> int:
    """Открыть сетку дня и окошки, добавленные вручную, не допуская пересечений.
    Добавленные вручную важнее: их открывают первыми, а пересекающееся с ними время сетки — нет."""
    items = await repo.day_slots(day)
    by_start = {item.slot.starts_at: item for item in items}
    grid = [datetime.combine(day, t) for t in grid_times(config)] if is_work_day(day, config) else []
    manual = sorted(item.slot.starts_at for item in items if item.slot.starts_at not in grid)
    opened = 0
    for starts in manual + grid:
        item = by_start.get(starts)
        if starts < now or (item and item.slot.is_open):
            continue
        minutes = item.slot.minutes if item else config.slot_minutes
        if find_clash(starts, minutes, items, now) is None:
            slot = await repo.put_slot(starts, minutes, is_open=True, auto=on_grid(starts, config))
            opened += 1
            if item:
                item.slot = slot
            else:
                items.append(DaySlot(slot, None))
    return opened


@router.callback_query(AdmWeek.filter())
async def week(callback: CallbackQuery, callback_data: AdmWeek, repo: Repo, clock: Clock, config: Settings) -> None:
    week_no = min(max(callback_data.week, 0), max_week(config))
    await show(callback, await week_screen(week_no, repo, clock, config))


@router.callback_query(AdmDay.filter())
async def day_action(callback: CallbackQuery, callback_data: AdmDay, callback_answer: CallbackAnswer,
                     state: FSMContext, repo: Repo, clock: Clock, config: Settings) -> None:
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
        if await open_all(day, repo, now, config):
            callback_answer.text = "Время на этот день открыто"
        else:
            callback_answer.text = "Открыть ничего не получилось: время пересекается с другими окошками"
    elif callback_data.action == "close_day":
        await repo.close_day(day, now)
        callback_answer.text = "День закрыт. Записи остались, их можно отменить по одной"

    await show(callback, await day_screen(day, repo, clock, config))


@router.callback_query(AdmSlot.filter())
async def slot_action(callback: CallbackQuery, callback_data: AdmSlot, callback_answer: CallbackAnswer,
                      repo: Repo, clock: Clock, config: Settings) -> None:
    now = clock.now()
    day = parse_day_key(callback_data.day)
    starts = datetime.strptime(f"{callback_data.day}{callback_data.hm}", "%Y%m%d%H%M")
    items = await repo.day_slots(day)
    item = next((i for i in items if i.slot.starts_at == starts), None)

    if item and item.booking:
        await show(callback, admin_screens.booking(item.booking, now, f"d{day_key(day)}"))
        return
    if starts < now:
        callback_answer.text = "Это время уже прошло"
    elif callback_data.to == "close":
        if item and item.slot.is_open and not await repo.close_slot_if_free(item.slot.id):
            callback_answer.text = "На это время только что записались"
        else:
            callback_answer.text = f"{hm(starts)} закрыто"
    elif callback_data.to == "open":
        minutes = item.slot.minutes if item else config.slot_minutes
        if item and item.slot.is_open:
            callback_answer.text = f"{hm(starts)} открыто"
        elif other := find_clash(starts, minutes, items, now):
            callback_answer.text = clash_text(other)
            callback_answer.show_alert = True
        else:
            await repo.put_slot(starts, minutes, is_open=True, auto=on_grid(starts, config))
            callback_answer.text = f"{hm(starts)} открыто"
    await show(callback, await day_screen(day, repo, clock, config))


@router.message(AdminInput.custom_time, TEXT)
async def got_custom_time(message: Message, state: FSMContext, repo: Repo, clock: Clock, config: Settings) -> None:
    data = await state.get_data()
    day = parse_day_key(data["day"])
    t = parse_time(message.text or "")
    if t is None:
        await message.answer("Не получилось разобрать время. Напишите, например, <i>15:30</i>.")
        return
    starts = datetime.combine(day, t)
    if starts < clock.now():
        await message.answer("Это время уже прошло. Напишите другое.")
        return
    items = await repo.day_slots(day)
    existing = next((i for i in items if i.slot.starts_at == starts), None)
    minutes = existing.slot.minutes if existing else config.slot_minutes
    if other := find_clash(starts, minutes, items, clock.now()):
        await message.answer(f"{clash_text(other)} или напишите другое время.")
        return
    await state.clear()
    await repo.put_slot(starts, minutes, is_open=True, auto=on_grid(starts, config))
    await message.answer(f"Окошко на {hm(t)} открыто.")
    await show(message, await day_screen(day, repo, clock, config))
