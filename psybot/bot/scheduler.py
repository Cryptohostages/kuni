"""Фоновые задачи: новые окошки по расписанию, напоминания ученикам, утренняя сводка психологу."""

import asyncio
import logging
from datetime import date, datetime, time, timedelta

from aiogram import Bot

from . import admin_screens, screens
from .config import Settings
from .db import Repo, Status, slot_starts
from .notify import notify_admins, send
from .reminders import DAY_BEFORE, soon_delta, will_remind_day, will_remind_soon
from .timeutil import Clock, grid_times, is_work_day

log = logging.getLogger(__name__)

TICK_SECONDS = 30
DIGEST_WINDOW = timedelta(hours=3)


async def fill_schedule(repo: Repo, today: date, config: Settings) -> int:
    if not config.auto_open:
        return 0
    days = [today + timedelta(days=i) for i in range(config.admin_days_ahead + 1)]
    days = [d for d in days if is_work_day(d, config)]
    return await repo.ensure_slots(slot_starts(days, grid_times(config)), config.slot_minutes)


async def send_reminders(bot: Bot, repo: Repo, now: datetime, config: Settings) -> None:
    soon = soon_delta(config)
    for booking in await repo.reminder_candidates(now, max(DAY_BEFORE, soon)):
        left = booking.starts_at - now

        if not booking.reminded_soon and left <= soon:
            if will_remind_soon(booking, config):
                await send(bot, booking.user.id, screens.remind_soon(booking, now.date(), config))
            await repo.mark_reminded(booking.id, day=True, soon=True)
            continue

        if not booking.reminded_day and left <= DAY_BEFORE:
            if will_remind_day(booking, config):
                await send(bot, booking.user.id, screens.remind_day(booking, now.date(), config))
            await repo.mark_reminded(booking.id, day=True)


async def send_digest(bot: Bot, repo: Repo, now: datetime, config: Settings) -> None:
    if config.digest_time is None or not config.admin_ids:
        return
    start = datetime.combine(now.date(), config.digest_time)
    if not start <= now < start + DIGEST_WINDOW:
        return
    if await repo.get_kv("digest_sent") == now.date().isoformat():
        return
    await repo.set_kv("digest_sent", now.date().isoformat())
    day_start = datetime.combine(now.date(), time.min)
    bookings = await repo.bookings_between(day_start, day_start + timedelta(days=1), [Status.ACTIVE])
    if bookings:
        await notify_admins(bot, config, admin_screens.digest(now.date(), bookings))


async def tick(bot: Bot, repo: Repo, clock: Clock, config: Settings, state: dict) -> None:
    now = clock.now()
    if state.get("filled") != now.date():
        added = await fill_schedule(repo, now.date(), config)
        if added:
            log.info("Открыто новых окошек по расписанию: %s", added)
        state["filled"] = now.date()
    await send_reminders(bot, repo, now, config)
    await send_digest(bot, repo, now, config)


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
