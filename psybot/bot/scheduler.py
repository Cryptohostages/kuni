"""Фоновые задачи: новые окошки по расписанию, напоминания ученикам, утренняя сводка психологу."""

import asyncio
import logging
from datetime import datetime, time, timedelta

from aiogram import Bot

from . import admin_screens, screens
from .config import Settings
from .db import Repo, Status, slot_starts
from .notify import Delivery, notify_admins, send
from .reminders import DAY_BEFORE, soon_delta, will_remind_day, will_remind_soon
from .timeutil import Clock, grid_times, is_work_day

log = logging.getLogger(__name__)

TICK_SECONDS = 30
DIGEST_WINDOW = timedelta(hours=3)
# через сколько после вопроса стирается, кто его задал (если на вопрос уже ответили или он скрыт)
FORGET_AUTHORS_AFTER = timedelta(days=1)


async def fill_schedule(repo: Repo, now: datetime, config: Settings) -> int:
    """Открыть окошки по сетке из настроек и убрать те, что остались от прежней сетки."""
    days = [now.date() + timedelta(days=i) for i in range(config.admin_days_ahead + 1)]
    starts = slot_starts([d for d in days if is_work_day(d, config)], grid_times(config)) if config.auto_open else []
    await repo.prune_auto_slots(now, set(starts), config.slot_minutes)
    return await repo.ensure_slots([dt for dt in starts if dt >= now], config.slot_minutes)


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
    if config.digest_time is None or not config.admin_ids:
        return
    start = datetime.combine(now.date(), config.digest_time)
    if not start <= now < start + DIGEST_WINDOW:
        return
    if await repo.get_kv("digest_sent") == now.date().isoformat():
        return
    day_start = datetime.combine(now.date(), time.min)
    bookings = await repo.bookings_between(day_start, day_start + timedelta(days=1), [Status.ACTIVE])
    if bookings:
        results = await notify_admins(bot, config, admin_screens.digest(now.date(), bookings))
        if Delivery.RETRY in results:
            return
    await repo.set_kv("digest_sent", now.date().isoformat())


async def tick(bot: Bot, repo: Repo, clock: Clock, config: Settings, state: dict) -> None:
    now = clock.now()
    if state.get("filled") != now.date():
        added = await fill_schedule(repo, now, config)
        if added:
            log.info("Открыто новых окошек по расписанию: %s", added)
        await repo.forget_authors(now - FORGET_AUTHORS_AFTER)
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
