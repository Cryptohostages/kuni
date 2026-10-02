import asyncio
from datetime import date, datetime, timedelta

from bot.db import BookResult, Status
from conftest import MONDAY_MORNING

NOW = MONDAY_MORNING
LATER = NOW + timedelta(hours=1)


async def make_user(repo, user_id=1, name="Аня Смирнова", class_name="8Б"):
    await repo.touch_user(user_id, None, "Аня", NOW)
    await repo.set_profile(user_id, name, class_name)


async def slot_at(repo, hour, day=None, is_open=True):
    day = day or NOW.date()
    return await repo.put_slot(datetime.combine(day, datetime.min.time()).replace(hour=hour), 45, is_open)


async def book(repo, user_id, slot_id, max_active=2):
    return await repo.create_booking(user_id, slot_id, "study", None, NOW, LATER, max_active)


async def test_booking_is_exclusive(repo):
    await make_user(repo, 1)
    await make_user(repo, 2)
    slot = await slot_at(repo, 11)

    results = await asyncio.gather(book(repo, 1, slot.id), book(repo, 2, slot.id))

    assert {r for r, _ in results} == {BookResult.OK, BookResult.TAKEN}
    assert await repo.free_slots(NOW.date(), LATER) == []


async def test_cancelled_slot_can_be_booked_again(repo):
    await make_user(repo, 1)
    await make_user(repo, 2)
    slot = await slot_at(repo, 11)
    _, booking_id = await book(repo, 1, slot.id)

    assert await repo.cancel_booking(booking_id, by_admin=False, reason=None, now=NOW)
    assert not await repo.cancel_booking(booking_id, by_admin=False, reason=None, now=NOW)
    result, _ = await book(repo, 2, slot.id)
    assert result is BookResult.OK


async def test_booking_rules(repo):
    await make_user(repo, 1)
    closed = await slot_at(repo, 12, is_open=False)
    too_soon = await slot_at(repo, 9)  # 9:00, а записываться можно не раньше 9:30
    assert (await book(repo, 1, closed.id))[0] is BookResult.UNAVAILABLE
    assert (await book(repo, 1, too_soon.id))[0] is BookResult.UNAVAILABLE
    assert (await book(repo, 1, 12345))[0] is BookResult.UNAVAILABLE

    first, second, third = [await slot_at(repo, h) for h in (13, 14, 15)]
    assert (await book(repo, 1, first.id))[0] is BookResult.OK
    assert (await book(repo, 1, second.id))[0] is BookResult.OK
    assert (await book(repo, 1, third.id))[0] is BookResult.LIMIT


async def test_free_days_and_overview(repo):
    await make_user(repo, 1)
    today, tomorrow = NOW.date(), NOW.date() + timedelta(days=1)
    a = await slot_at(repo, 11)
    await slot_at(repo, 12)
    await slot_at(repo, 8)  # уже прошло
    await slot_at(repo, 11, day=tomorrow, is_open=False)
    await book(repo, 1, a.id)

    assert await repo.free_days(LATER, tomorrow) == [(today, 1)]
    overview = await repo.days_overview(today, tomorrow, NOW)
    assert overview[today] == (1, 1)
    assert overview[tomorrow] == (0, 0)


async def test_close_slot_only_if_free(repo):
    await make_user(repo, 1)
    free, taken = await slot_at(repo, 11), await slot_at(repo, 12)
    await book(repo, 1, taken.id)
    assert await repo.close_slot_if_free(free.id)
    assert not await repo.close_slot_if_free(taken.id)
    assert (await repo.get_slot(taken.id)).is_open


async def test_close_and_open_day_keeps_bookings(repo):
    await make_user(repo, 1)
    for hour in (10, 11, 12):
        await slot_at(repo, hour)
    taken = await slot_at(repo, 13)
    await book(repo, 1, taken.id)

    assert await repo.set_day_free_slots(NOW.date(), NOW, is_open=False) == 3
    assert (await repo.get_slot(taken.id)).is_open
    assert await repo.free_slots(NOW.date(), LATER) == []
    assert await repo.set_day_free_slots(NOW.date(), NOW, is_open=True) == 3


async def test_status_marks_and_month(repo):
    await make_user(repo, 1)
    slot = await slot_at(repo, 11)
    _, booking_id = await book(repo, 1, slot.id)
    assert await repo.set_status(booking_id, Status.DONE)
    assert await repo.set_status(booking_id, Status.MISSED)
    month = await repo.month_bookings(NOW.year, NOW.month)
    assert [b.status for b in month] == [Status.MISSED]
    assert await repo.month_bookings(NOW.year, NOW.month + 1) == []


async def test_ensure_slots_is_idempotent_and_respects_closed(repo):
    starts = [datetime(2026, 10, 6, 10), datetime(2026, 10, 6, 11)]
    assert await repo.ensure_slots(starts, 45) == 2
    slot = await repo.get_slot_at(starts[0])
    await repo.set_day_free_slots(date(2026, 10, 6), NOW, is_open=False)
    assert await repo.ensure_slots(starts, 45) == 0
    assert not (await repo.get_slot(slot.id)).is_open


async def test_questions(repo):
    await make_user(repo, 1)
    qid = await repo.add_question(1, "Как перестать волноваться?", NOW)
    assert await repo.questions_since(1, NOW - timedelta(days=1)) == 1
    assert [q.id for q in await repo.new_questions()] == [qid]
    assert await repo.answer_question(qid, "Приходи", NOW)
    assert not await repo.answer_question(qid, "Ещё раз", NOW)
    assert await repo.new_questions() == []
