from datetime import datetime, timedelta

from bot import scheduler
from bot.db import Status
from conftest import ADMIN, STUDENT, make_config


async def booked(h, starts: datetime, created: datetime) -> int:
    await h.repo.touch_user(STUDENT, None, "Аня", created)
    await h.repo.set_profile(STUDENT, "Аня Смирнова", "8Б")
    slot = await h.repo.put_slot(starts, 45, True)
    _, booking_id = await h.repo.create_booking(STUDENT, slot.id, "study", None, created, created, 2)
    return booking_id


async def run_at(h, when: datetime) -> list[str]:
    before = len(h.chat(STUDENT))
    h.clock.current = when
    await scheduler.send_reminders(h.bot, h.repo, when, h.config)
    return [m.text for m in h.chat(STUDENT)[before:]]


async def test_day_and_hour_reminders(h):
    starts = datetime(2026, 10, 7, 11, 0)
    await booked(h, starts, created=datetime(2026, 10, 5, 9, 0))

    assert await run_at(h, starts - timedelta(hours=25)) == []
    day = await run_at(h, starts - timedelta(hours=24))
    assert len(day) == 1 and "Завтра в 11:00" in day[0] and "кабинет 214" in day[0]
    assert await run_at(h, starts - timedelta(hours=23)) == []
    soon = await run_at(h, starts - timedelta(minutes=60))
    assert len(soon) == 1 and "сегодня в 11:00" in soon[0]
    assert await run_at(h, starts - timedelta(minutes=30)) == []


async def test_fresh_booking_gets_only_hour_reminder(h):
    starts = datetime(2026, 10, 6, 11, 0)
    await booked(h, starts, created=datetime(2026, 10, 5, 12, 0))  # за 23 часа
    assert await run_at(h, datetime(2026, 10, 5, 12, 1)) == []
    assert len(await run_at(h, starts - timedelta(minutes=59))) == 1


async def test_last_minute_booking_gets_nothing(h):
    starts = datetime(2026, 10, 5, 11, 0)
    await booked(h, starts, created=datetime(2026, 10, 5, 10, 30))
    assert await run_at(h, datetime(2026, 10, 5, 10, 31)) == []


async def test_cancelled_booking_is_not_reminded(h):
    starts = datetime(2026, 10, 7, 11, 0)
    booking_id = await booked(h, starts, created=datetime(2026, 10, 5, 9, 0))
    await h.repo.cancel_booking(booking_id, by_admin=False, reason=None, now=datetime(2026, 10, 5, 9, 1))
    assert await run_at(h, starts - timedelta(hours=24)) == []


async def test_reminder_keep_button_removes_keyboard(h):
    starts = datetime(2026, 10, 7, 11, 0)
    await booked(h, starts, created=datetime(2026, 10, 5, 9, 0))
    await run_at(h, starts - timedelta(hours=24))
    await h.press(STUDENT, "Приду")
    assert h.last(STUDENT).markup is None
    assert h.last_alert == "Отлично, до встречи!"


async def test_reminder_cancel_button(h):
    starts = datetime(2026, 10, 7, 11, 0)
    booking_id = await booked(h, starts, created=datetime(2026, 10, 5, 9, 0))
    await run_at(h, starts - timedelta(hours=24))
    await h.press(STUDENT, "Отменить")
    await h.press(STUDENT, "Да, отменить")
    assert (await h.repo.get_booking(booking_id)).status is Status.CANCELLED
    assert "отменена учеником" in h.last(ADMIN).text


async def test_digest_once_a_day_and_only_in_window(h):
    await booked(h, datetime(2026, 10, 5, 11, 0), created=datetime(2026, 10, 1, 9, 0))
    await scheduler.send_digest(h.bot, h.repo, datetime(2026, 10, 5, 7, 59), h.config)
    assert h.chat(ADMIN) == []
    await scheduler.send_digest(h.bot, h.repo, datetime(2026, 10, 5, 8, 0), h.config)
    await scheduler.send_digest(h.bot, h.repo, datetime(2026, 10, 5, 8, 30), h.config)
    assert len(h.chat(ADMIN)) == 1
    assert "Сегодня 1 встреча" in h.last(ADMIN).text and "Аня Смирнова, 8Б" in h.last(ADMIN).text


async def test_digest_skipped_when_bot_started_late(h):
    await booked(h, datetime(2026, 10, 5, 15, 0), created=datetime(2026, 10, 1, 9, 0))
    await scheduler.send_digest(h.bot, h.repo, datetime(2026, 10, 5, 13, 0), h.config)
    assert h.chat(ADMIN) == []


async def test_fill_schedule_only_work_days(repo):
    config = make_config()
    monday = datetime(2026, 10, 5).date()
    await scheduler.fill_schedule(repo, monday, config)
    overview = await repo.days_overview(monday, monday + timedelta(days=6), datetime(2026, 10, 5, 0, 0))
    assert sorted(d.isoweekday() for d in overview) == [1, 2, 3, 4, 5]
    assert all(free == 8 for free, _ in overview.values())


async def test_fill_schedule_disabled(repo):
    config = make_config(auto_open=False)
    assert await scheduler.fill_schedule(repo, datetime(2026, 10, 5).date(), config) == 0
