"""Неочевидные ситуации: двойные нажатия, старые кнопки, сбои Telegram, смена расписания."""

import logging
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendMessage
from aiogram.types import Chat

from bot import scheduler
from bot.callbacks import AdmSlot, BookConfirm
from bot.db import Status
from conftest import ADMIN, OTHER, STUDENT, make_config
from test_flows import register_and_book


async def ask_and_open_reply(h, text="Как справиться с тревогой перед контрольной?"):
    await h.send(STUDENT, "/ask")
    await h.send(STUDENT, text)
    await h.press(ADMIN, "✍️ Ответить")


# --- запись -----------------------------------------------------------------------


async def test_double_tap_confirm_books_once_and_keeps_success_screen(h):
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "10:00")
    await h.press(STUDENT, "Семья")
    await h.send(STUDENT, "Аня Смирнова")
    await h.send(STUDENT, "8Б")
    confirm, button = h.find_button(STUDENT, "✅ Записаться")
    await h.press_data(STUDENT, confirm, button.callback_data)
    await h.press_data(STUDENT, confirm, button.callback_data)

    assert "Запись готова" in confirm.text
    assert len(await h.repo.upcoming_for_user(STUDENT, h.clock.now())) == 1
    assert sum("Новая запись" in m.text for m in h.chat(ADMIN)) == 1
    assert not any(show_alert for _, show_alert in h.session.alerts)


async def test_old_confirm_button_does_not_book_another_slot(h):
    await register_and_book(h, hour="10:00")  # профиль уже есть
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "11:00")
    await h.press(STUDENT, "Семья")
    old_confirm, old_button = h.find_button(STUDENT, "✅ Записаться")

    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "12:00")  # новый процесс записи
    await h.press_data(STUDENT, old_confirm, old_button.callback_data)

    times = [b.starts_at.hour for b in await h.repo.upcoming_for_user(STUDENT, h.clock.now())]
    assert times == [10]


async def test_comment_can_be_removed(h):
    await register_and_book(h, hour="10:00")
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "11:00")
    await h.press(STUDENT, "Другое")
    await h.press(STUDENT, "✏️ Комментарий")
    await h.send(STUDENT, "лишнее")
    assert "лишнее" in h.last(STUDENT).text
    await h.press(STUDENT, "✏️ Комментарий")
    await h.press(STUDENT, "🗑 Убрать")
    assert "лишнее" not in h.last(STUDENT).text and "Проверь" in h.last(STUDENT).text


async def test_back_from_name_prompt_keeps_booking(h):
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "10:00")
    await h.press(STUDENT, "Семья")
    await h.press(STUDENT, "← Назад")
    assert "О чём хочется поговорить" in h.last(STUDENT).text
    await h.press(STUDENT, "Учёба и нагрузка")
    await h.send(STUDENT, "Аня Смирнова")
    await h.send(STUDENT, "8Б")
    assert "Учёба и нагрузка" in h.last(STUDENT).text


async def test_too_many_bookings_in_a_day(h):
    h.config.max_active_bookings = 10
    for hour in ("10:00", "11:00", "12:00", "13:00", "14:00", "15:00"):
        await register_and_book(h, hour=hour)
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "16:00")
    await h.press(STUDENT, "Семья")
    await h.press(STUDENT, "✅ Записаться")
    assert "Сегодня записей было уже много" in h.last(STUDENT).text
    assert sum("Новая запись" in m.text for m in h.chat(ADMIN)) == 6


async def test_admin_cancel_closes_time_and_keeps_notice(h):
    await register_and_book(h, hour="13:00")
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "📋 Записи")
    await h.press(ADMIN, "13:00 · Аня Смирнова")
    await h.press(ADMIN, "Отменить запись")
    await h.send(ADMIN, "Заболела")

    notice = h.last(STUDENT)
    await h.press(STUDENT, "Выбрать другое время")
    assert "Заболела" in notice.text, "уведомление об отмене не должно затираться"
    assert "13:00" not in [b.text for b in h.last(STUDENT).buttons + h.chat(STUDENT)[-1].buttons]
    await h.send(OTHER, "/book")
    await h.press(OTHER, "Сегодня")
    assert "13:00" not in [b.text for b in h.last(OTHER).buttons]


async def test_closed_day_stays_closed_after_cancellations(h):
    await register_and_book(h, day="Вт, 6 окт", hour="10:00")
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Вт, 6 окт")
    await h.press(ADMIN, "Закрыть день")
    await h.press(ADMIN, "👤 10:00")
    await h.press(ADMIN, "Отменить запись")
    await h.press(ADMIN, "Отменить без причины")

    await h.send(OTHER, "/book")
    assert not any(b.text.startswith("Вт, 6 окт") for b in h.last(OTHER).buttons)


async def test_student_cancel_on_closed_day_does_not_reopen(h):
    await register_and_book(h, day="Вт, 6 окт", hour="10:00")
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Вт, 6 окт")
    await h.press(ADMIN, "Закрыть день")
    await h.send(STUDENT, "/my")
    await h.press(STUDENT, "Завтра, 10:00")
    await h.press(STUDENT, "Отменить запись")
    await h.press(STUDENT, "Да, отменить")
    assert "снова свободно" not in h.last(STUDENT).text
    assert "отменена учеником" in h.last(ADMIN).text and "снова свободно" not in h.last(ADMIN).text
    await h.send(OTHER, "/book")
    assert not any(b.text.startswith("Вт, 6 окт") for b in h.last(OTHER).buttons)


# --- кнопки и состояния ------------------------------------------------------------


async def test_button_press_ends_text_input(h):
    starts = datetime(2026, 10, 7, 11, 0)
    await register_and_book(h, day="Ср, 7 окт", hour="11:00")
    h.clock.current = starts - timedelta(hours=24)
    await scheduler.send_reminders(h.bot, h.repo, h.clock.now(), h.config)
    await h.send(STUDENT, "/ask")
    await h.press(STUDENT, "Приду")
    await h.send(STUDENT, "ок, приду")
    assert await h.repo.new_questions() == []


async def test_keep_after_admin_cancel_is_not_cheerful(h):
    starts = datetime(2026, 10, 7, 11, 0)
    await register_and_book(h, day="Ср, 7 окт", hour="11:00")
    h.clock.current = starts - timedelta(hours=24)
    await scheduler.send_reminders(h.bot, h.repo, h.clock.now(), h.config)
    booking_id = (await h.repo.upcoming_for_user(STUDENT, h.clock.now()))[0].id
    await h.repo.cancel_booking(booking_id, by_admin=True, reason=None, now=h.clock.now())
    await h.press(STUDENT, "Приду")
    assert h.last_alert == "Эта запись уже неактуальна"


async def test_soon_reminder_has_cancel_button(h):
    starts = datetime(2026, 10, 7, 11, 0)
    await register_and_book(h, day="Ср, 7 окт", hour="11:00")
    h.clock.current = starts - timedelta(minutes=50)
    await scheduler.send_reminders(h.bot, h.repo, h.clock.now(), h.config)
    await h.press(STUDENT, "Не получится прийти")
    await h.press(STUDENT, "Да, отменить")
    assert "Запись отменена" in h.last(STUDENT).text


async def test_crash_shows_alert(h, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("тест")

    await h.send(STUDENT, "/start")
    monkeypatch.setattr(h.repo, "free_days", boom)
    await h.press(STUDENT, "Записаться на встречу")
    assert h.session.alerts[-1] == ("Что-то пошло не так. Попробуй ещё раз или начни сначала: /start", True)


async def test_group_chats_are_ignored(h):
    await h.send(STUDENT, "/start", chat=Chat(id=-100500, type="supergroup"))
    await h.send(STUDENT, "/help", chat=Chat(id=-100500, type="supergroup"))
    assert not any(isinstance(m, SendMessage) for _, m in h.session.log)


# --- анонимные вопросы ------------------------------------------------------------


async def test_buttons_under_answer_do_not_erase_it(h):
    await ask_and_open_reply(h)
    await h.send(ADMIN, "Приходи, разберём по шагам.")
    answer = h.last(STUDENT)
    await h.press(STUDENT, "🗓 Записаться на встречу")
    assert "разберём по шагам" in answer.text
    assert "Запись к психологу" in h.last(STUDENT).text and h.last(STUDENT) is not answer


async def test_too_long_answer_is_not_lost(h):
    await ask_and_open_reply(h, "Вопрос " * 280)
    await h.send(ADMIN, "Ответ " * 600)
    assert "помещается до 3000" in h.last(ADMIN).text
    await h.send(ADMIN, "Короткий ответ")
    assert "Короткий ответ" in h.last(STUDENT).text


async def test_answer_is_kept_for_retry_on_network_error(h):
    await ask_and_open_reply(h)
    h.session.failures[STUDENT] = TelegramNetworkError(method=None, message="timeout")
    await h.send(ADMIN, "Ответ")
    assert any("Вопрос остался в списке" in m.text for m in h.chat(ADMIN))
    assert len(await h.repo.new_questions()) == 1


async def test_failed_delivery_does_not_log_author(h, caplog):
    caplog.set_level(logging.INFO)
    await ask_and_open_reply(h)
    h.session.failures[STUDENT] = TelegramForbiddenError(method=None, message="bot was blocked by the user")
    await h.send(ADMIN, "Ответ")
    assert any("автор остановил бота" in m.text for m in h.chat(ADMIN))
    assert str(STUDENT) not in caplog.text


async def test_authors_are_forgotten_after_a_day(h):
    await ask_and_open_reply(h)
    await h.send(ADMIN, "Ответ")
    question = (await h.repo.get_question(1))
    assert question.user_id == STUDENT
    h.clock.current += timedelta(days=1, hours=1)
    await scheduler.tick(h.bot, h.repo, h.clock, h.config, {})
    assert (await h.repo.get_question(1)).user_id is None


async def test_question_card_has_no_exact_time(h):
    await h.send(STUDENT, "/ask")
    await h.send(STUDENT, "Вопрос про экзамены")
    await h.press(ADMIN, "Открыть")
    assert "08:30" not in h.last(ADMIN).text


# --- окошки психолога -------------------------------------------------------------


async def test_double_tap_close_stays_closed(h):
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Вт, 6 окт")
    screen = h.last(ADMIN)
    data = AdmSlot(day="20261006", hm="1200", to="close").pack()
    await h.press_data(ADMIN, screen, data)
    await h.press_data(ADMIN, screen, data)
    assert not (await h.repo.get_slot_at(datetime(2026, 10, 6, 12, 0))).is_open


async def test_custom_time_cannot_overlap(h):
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Вт, 6 окт")
    await h.press(ADMIN, "Другое время")
    await h.send(ADMIN, "10:30")
    assert "Пересекается с 10:00–10:45" in h.last(ADMIN).text
    await h.press(ADMIN, "Отмена")
    await h.press(ADMIN, "🟢 10:00")
    await h.press(ADMIN, "Другое время")
    await h.send(ADMIN, "10:30")
    assert "Пересекается с 11:00–11:45" in h.last(ADMIN).text
    await h.send(ADMIN, "10:10")
    assert "🟢 10:10" in [b.text for b in h.last(ADMIN).buttons]
    await h.press(ADMIN, "▫️ 10:00")
    assert "Пересекается" in h.last_alert
    await h.press(ADMIN, "Закрыть день")
    await h.press(ADMIN, "Открыть всё")
    opened = [b.text for b in h.last(ADMIN).buttons if b.text.startswith("🟢")]
    assert "🟢 10:10" in opened and "🟢 10:00" not in opened and "🟢 11:00" in opened


async def test_week_view_reaches_last_bookable_day(h):
    h.config.booking_days_ahead = 28
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    for _ in range(4):
        await h.press(ADMIN, "Дальше ›")
    labels = [b.text for b in h.last(ADMIN).buttons]
    assert any(label.startswith("Пн, 2 ноя") for label in labels)
    assert "Дальше ›" not in labels


async def test_schedule_change_removes_old_grid(h):
    await register_and_book(h, day="Вт, 6 окт", hour="10:00")
    new = make_config(work_days="1,3,5", day_start="09:30", day_end="17:30")
    await scheduler.fill_schedule(h.repo, h.clock.now(), new)

    tuesday = await h.repo.day_slots(datetime(2026, 10, 6).date())
    assert [(i.slot.starts_at.hour, i.booking is not None) for i in tuesday] == [(10, True)]
    wednesday = await h.repo.free_slots(datetime(2026, 10, 7).date(), h.clock.now())
    assert [s.starts_at.strftime("%H:%M") for s in wednesday] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30",
    ]


async def test_auto_open_off_removes_generated_slots(h):
    await scheduler.fill_schedule(h.repo, h.clock.now(), make_config(auto_open=False))
    assert await h.repo.free_days(h.clock.now(), h.clock.now().date() + timedelta(days=30)) == []


async def test_journal_counts_add_up(h):
    await register_and_book(h, hour="10:00")
    await register_and_book(h, hour="11:00")
    booking_id = (await h.repo.upcoming_for_user(STUDENT, h.clock.now()))[0].id
    h.clock.current = datetime(2026, 10, 5, 12, 0)
    await h.repo.set_status(booking_id, Status.DONE)
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "📄 Журнал")
    text = h.last(ADMIN).text
    assert "Октябрь 2026: 2 встречи" in text and "Состоялось — 1, без отметки — 1" in text


async def test_stale_comment_button_from_other_flow(h):
    await register_and_book(h, hour="10:00")
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "11:00")
    screen = h.last(STUDENT)
    await h.press_data(STUDENT, screen, BookConfirm(action="comment", slot=999).pack())
    assert h.last_alert == "Это время уже недоступно, выбери другое"
