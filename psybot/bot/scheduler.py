"""Фоновые задачи: новые окошки по расписанию, напоминания ученикам, утренняя сводка психологу."""

import asyncio
import logging
from datetime import date, datetime, time, timedelta

from aiogram import Bot

from . import admin_screens, screens
from .config import Settings
from .db import Repo, Status, find_clash
from .notify import Delivery, send
from .reminders import DAY_BEFORE, soon_delta, will_remind_day, will_remind_soon
from .timeutil import Clock, grid_times, is_work_day

log = logging.getLogger(__name__)

TICK_SECONDS = 30
DIGEST_WINDOW = timedelta(hours=3)
# через сколько после ответа (или скрытия) стирается, кто задал вопрос
FORGET_AUTHORS_AFTER = timedelta(days=1)


async def fill_schedule(repo: Repo, now: datetime, config: Settings) -> int:
    """Открыть окошки по сетке из настроек на несколько недель вперёд.
    Если сетку в .env поменяли, свободные окошки старой сетки убираются, а новые не открываются
    поверх записей и окошков, открытых вручную, и не открывают того, что психолог закрыл."""
    days = [now.date() + timedelta(days=i) for i in range(config.admin_days_ahead + 1)]
    grid = grid_times(config) if config.auto_open else []
    plan = {d: [datetime.combine(d, t) for t in grid] for d in days if is_work_day(d, config)}

    closed_days: set[date] = set()
    closed_ranges: dict[date, list[tuple[datetime, datetime]]] = {}
    for d in plan:
        future = [i.slot for i in await repo.day_slots(d) if i.slot.starts_at >= now]
        if future and not any(slot.is_open for slot in future):
            closed_days.add(d)
        closed_ranges[d] = [
            (slot.starts_at, slot.starts_at + timedelta(minutes=slot.minutes)) for slot in future if not slot.is_open
        ]

    await repo.prune_auto_slots(now, {dt for starts in plan.values() for dt in starts}, config.slot_minutes)

    to_open: list[datetime] = []
    to_close: list[datetime] = []
    for d, starts in plan.items():
        items = await repo.day_slots(d)
        existing = {i.slot.starts_at for i in items}
        for dt in starts:
            if dt < now or dt in existing or find_clash(dt, config.slot_minutes, items, now):
                continue
            end = dt + timedelta(minutes=config.slot_minutes)
            if d in closed_days or any(a < end and dt < b for a, b in closed_ranges[d]):
                to_close.append(dt)
            else:
                to_open.append(dt)
    await repo.ensure_slots(to_close, config.slot_minutes, is_open=False)
    return await repo.ensure_slots(to_open, config.slot_minutes)


async def send_reminders(bot: Bot, repo: Repo, now: datetime, config: Settings) -> None:
    soon = soon_delta(config)
    for booking in await repo.reminder_candidates(now, max(DAY_BEFORE, soon)):
        left = booking.starts_at - now

        # если Telegram сейчас недоступен, не помечаем: попробуем на следующем круге
        if not booking.reminded_soon and left <= soon:
            if will_remind_soon(booking, config):
                screen = screens.remind_soon(booking, now.date(), config)
                if await send(bot, booking.user.id, screen) is Delivery.RETRY:
                    continue
            await repo.mark_reminded(booking.id, day=True, soon=True)
            continue

        if not booking.reminded_day and left <= DAY_BEFORE:
            if will_remind_day(booking, config):
                screen = screens.remind_day(booking, now.date(), config)
                if await send(bot, booking.user.id, screen) is Delivery.RETRY:
                    continue
            await repo.mark_reminded(booking.id, day=True)


async def send_digest(bot: Bot, repo: Repo, now: datetime, config: Settings) -> None:
    if config.digest_time is None:
        return
    start = datetime.combine(now.date(), config.digest_time)
    if not start <= now < start + DIGEST_WINDOW:
        return
    today = now.date().isoformat()
    pending = [a for a in config.admin_ids if await repo.get_kv(f"digest_sent:{a}") != today]
    if not pending:
        return
    day_start = datetime.combine(now.date(), time.min)
    bookings = await repo.bookings_between(day_start, day_start + timedelta(days=1), [Status.ACTIVE])
    for admin_id in pending:
        if bookings:
            delivery = await send(bot, admin_id, admin_screens.digest(now.date(), bookings))
            if delivery is Delivery.RETRY:
                continue
        await repo.set_kv(f"digest_sent:{admin_id}", today)


async def tick(bot: Bot, repo: Repo, clock: Clock, config: Settings, state: dict) -> None:
    """Один круг фоновых задач. Каждая в своём try: сбой одной не должен останавливать остальные."""
    now = clock.now()
    if state.get("filled") != now.date():
        try:
            added = await fill_schedule(repo, now, config)
            if added:
                log.info("Открыто новых окошек по расписанию: %s", added)
            state["filled"] = now.date()
        except Exception:
            log.exception("Не удалось обновить окошки по расписанию")
    for job in (repo.forget_authors(now - FORGET_AUTHORS_AFTER), send_reminders(bot, repo, now, config),
                send_digest(bot, repo, now, config)):
        try:
            await job
        except Exception:
            log.exception("Ошибка в фоновой задаче")


async def run(bot: Bot, repo: Repo, clock: Clock, config: Settings) -> None:
    state: dict = {}
    while True:
        try:
            await tick(bot, repo, clock, config, state)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка в фоновой задаче")
        await asyncio.sleep(TICK_SECONDS)
