"""Сквозные сценарии: человек нажимает кнопки, проверяем, что он видит."""

import csv
import io
from datetime import datetime, timedelta

from aiogram.fsm.storage.memory import MemoryStorage

from bot.callbacks import AdmBooking, MyBooking
from bot.db import Status
from conftest import ADMIN, OTHER, STUDENT


async def register_and_book(h, user_id=STUDENT, day="Сегодня", hour="10:00", name="аня смирнова", klass="8б"):
    await h.send(user_id, "/start")
    await h.press(user_id, "Записаться на встречу")
    await h.press(user_id, day)
    await h.press(user_id, hour)
    await h.press(user_id, "Учёба и нагрузка")
    user = await h.repo.get_user(user_id)
    if not user.has_profile:
        await h.send(user_id, name)
        await h.send(user_id, klass)
    await h.press(user_id, "✅ Записаться")


async def test_full_booking(h):
    await register_and_book(h)

    screen = h.last(STUDENT)
    assert "Запись готова" in screen.text
    assert "Понедельник, 5 октября" in screen.text and "10:00–10:45" in screen.text
    notice = h.last(ADMIN).text
    assert "Новая запись" in notice and "Аня Смирнова" in notice and "8Б" in notice
    assert "Учёба и нагрузка" in notice

    user = await h.repo.get_user(STUDENT)
    assert (user.full_name, user.class_name) == ("Аня Смирнова", "8Б")

    await h.send(STUDENT, "/start")
    assert "Ближайшая встреча: <b>сегодня, 10:00</b>" in h.last(STUDENT).text


async def test_whole_flow_edits_one_message(h):
    """Навигация кнопками не плодит сообщения: экран переписывается на месте."""
    await h.send(STUDENT, "/start")
    first = h.last(STUDENT).message_id
    await h.press(STUDENT, "Записаться на встречу")
    await h.press(STUDENT, "Вт, 6 окт")
    await h.press(STUDENT, "← Другой день")
    await h.press(STUDENT, "← В меню")
    await h.press(STUDENT, "О психологе")
    assert len(h.chat(STUDENT)) == 1 and h.last(STUDENT).message_id == first
    assert "Мария Ивановна Соколова" in h.last(STUDENT).text


async def test_comment_and_name_change_before_confirm(h):
    await register_and_book(h, hour="11:00")  # первая запись, чтобы профиль уже был
    await h.press(STUDENT, "← В меню")
    await h.press(STUDENT, "Записаться на встречу")
    await h.press(STUDENT, "Вт, 6 окт")
    await h.press(STUDENT, "12:00")
    await h.press(STUDENT, "Не хочу уточнять")
    await h.press(STUDENT, "✏️ Комментарий")
    await h.send(STUDENT, "Хочу обсудить нагрузку <перед ОГЭ>")
    assert "<i>Хочу обсудить нагрузку &lt;перед ОГЭ&gt;</i>" in h.last(STUDENT).text
    await h.press(STUDENT, "Имя и класс")
    await h.send(STUDENT, "Анна Смирнова")
    await h.send(STUDENT, "9А")
    confirm = h.last(STUDENT).text
    assert "Анна Смирнова, 9А" in confirm and "перед ОГЭ" in confirm and "💬" not in confirm
    await h.press(STUDENT, "✅ Записаться")
    assert "Запись готова" in h.last(STUDENT).text
    assert "Хочу обсудить нагрузку" in h.last(ADMIN).text


async def test_slot_taken_while_choosing(h):
    await h.send(OTHER, "/start")
    await h.press(OTHER, "Записаться на встречу")
    await h.press(OTHER, "Сегодня")

    await register_and_book(h, hour="14:00")

    await h.press(OTHER, "14:00")
    assert h.last_alert == "Это время уже недоступно, выбери другое"
    assert "14:00" not in [b.text for b in h.last(OTHER).buttons]


async def test_slot_taken_at_confirm(h):
    await register_and_book(h, user_id=OTHER, hour="15:00", name="Петя Иванов", klass="9В")
    await h.send(OTHER, "/my")
    booking_id = (await h.repo.upcoming_for_user(OTHER, h.clock.now()))[0].id
    await h.repo.cancel_booking(booking_id, by_admin=False, reason=None, now=h.clock.now())

    # Аня дошла до подтверждения, а Петя в это время записался обратно
    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "15:00")
    await h.press(STUDENT, "Семья")
    await h.send(STUDENT, "Аня Смирнова")
    await h.send(STUDENT, "8Б")
    slot = await h.repo.get_slot_at(datetime(2026, 10, 5, 15, 0))
    now = h.clock.now()
    await h.repo.create_booking(OTHER, slot.id, None, None, now, now, now.date() + timedelta(days=14), 2, 6)

    await h.press(STUDENT, "✅ Записаться")
    assert h.session.alerts[-1] == ("Это время только что заняли. Выбери другое", True)
    assert await h.repo.upcoming_for_user(STUDENT, h.clock.now()) == []


async def test_limit_of_active_bookings(h):
    await register_and_book(h, hour="10:00")
    await register_and_book(h, hour="11:00")
    await h.press(STUDENT, "← В меню")
    await h.press(STUDENT, "Записаться на встречу")
    assert "У тебя уже 2 записи" in h.last(STUDENT).text


async def test_student_cancels(h):
    await register_and_book(h)
    await h.send(STUDENT, "/my")
    assert "сегодня, 10:00" in h.last(STUDENT).text
    await h.press(STUDENT, "Сегодня, 10:00")
    await h.press(STUDENT, "Отменить запись")
    assert "Отменить встречу сегодня в 10:00?" in h.last(STUDENT).text
    await h.press(STUDENT, "Да, отменить")
    assert "Запись отменена" in h.last(STUDENT).text
    assert "Запись отменена учеником" in h.last(ADMIN).text
    assert await h.repo.upcoming_for_user(STUDENT, h.clock.now()) == []

    # время снова свободно
    await h.send(OTHER, "/book")
    await h.press(OTHER, "Сегодня")
    assert "10:00" in [b.text for b in h.last(OTHER).buttons]


async def test_cannot_touch_someone_elses_booking(h):
    await register_and_book(h)
    booking_id = (await h.repo.upcoming_for_user(STUDENT, h.clock.now()))[0].id
    await h.send(OTHER, "/start")
    await h.press_data(OTHER, h.last(OTHER), MyBooking(id=booking_id, action="cancel_yes").pack())
    assert (await h.repo.get_booking(booking_id)).status is Status.ACTIVE
    assert h.last_alert == "Эта кнопка устарела. Начни заново из меню."


async def test_non_admin_cannot_open_cabinet(h):
    await register_and_book(h)
    booking_id = (await h.repo.upcoming_for_user(STUDENT, h.clock.now()))[0].id
    await h.send(OTHER, "/admin")
    assert "Кабинет психолога" not in h.last(OTHER).text
    await h.press_data(OTHER, h.last(OTHER), AdmBooking(id=booking_id, action="no_reason").pack())
    assert (await h.repo.get_booking(booking_id)).status is Status.ACTIVE
    await h.send(OTHER, "/start")
    assert "Кабинет психолога" not in [b.text for b in h.last(OTHER).buttons]


async def test_admin_sees_records_and_cancels_with_reason(h):
    await register_and_book(h, hour="13:00")
    await h.send(ADMIN, "/admin")
    panel = h.last(ADMIN).text
    assert "Записей сегодня: <b>1</b>, ближайшая в 13:00" in panel
    await h.press(ADMIN, "📋 Записи")
    assert "13:00  Аня Смирнова, 8Б" in h.last(ADMIN).text
    await h.press(ADMIN, "13:00 · Аня Смирнова")
    assert "Запись #" in h.last(ADMIN).text and "tg://user?id=501" in h.last(ADMIN).text
    await h.press(ADMIN, "Отменить запись")
    await h.send(ADMIN, "Заболела, перенесём на четверг")

    to_student = h.chat(STUDENT)[-1].text
    assert "Встреча отменена" in to_student and "Заболела, перенесём на четверг" in to_student
    assert "отменена психологом" in h.last(ADMIN).text


async def test_admin_marks_attendance_after_meeting(h):
    await register_and_book(h, hour="10:00")
    booking_id = (await h.repo.upcoming_for_user(STUDENT, h.clock.now()))[0].id
    h.clock.current = datetime(2026, 10, 5, 11, 0)
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "📋 Записи")
    await h.press(ADMIN, "10:00 · Аня Смирнова")
    assert "Отменить запись" not in [b.text for b in h.last(ADMIN).buttons]
    await h.press(ADMIN, "✓ Состоялась")
    assert (await h.repo.get_booking(booking_id)).status is Status.DONE
    assert "встреча состоялась" in h.last(ADMIN).text


async def test_admin_toggles_slots(h):
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    week = h.last(ADMIN)
    assert "Сегодня · 🟢 8" in [b.text for b in week.buttons]
    assert "Сб, 10 окт · выходной" in [b.text for b in week.buttons]

    await h.press(ADMIN, "Вт, 6 окт")
    await h.press(ADMIN, "🟢 12:00")
    assert h.last_alert == "12:00 закрыто"
    assert "▫️ 12:00" in [b.text for b in h.last(ADMIN).buttons]

    await h.send(STUDENT, "/book")
    await h.press(STUDENT, "Вт, 6 окт")
    assert "12:00" not in [b.text for b in h.last(STUDENT).buttons]

    await h.press(ADMIN, "▫️ 12:00")
    assert h.last_alert == "12:00 открыто"
    await h.press(ADMIN, "Закрыть день")
    assert not any(b.text.startswith("🟢") for b in h.last(ADMIN).buttons)
    await h.press(ADMIN, "Открыть всё")
    assert sum(b.text.startswith("🟢") for b in h.last(ADMIN).buttons) == 8


async def test_admin_adds_custom_time_on_weekend(h):
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Сб, 10 окт")
    await h.press(ADMIN, "Другое время")
    await h.send(ADMIN, "abc")
    assert "Не получилось разобрать время" in h.last(ADMIN).text
    await h.send(ADMIN, "11:30")
    assert "🟢 11:30" in [b.text for b in h.last(ADMIN).buttons]

    await h.send(STUDENT, "/book")
    assert "Сб, 10 окт · 1" in [b.text for b in h.last(STUDENT).buttons]


async def test_booked_slot_opens_booking_from_day_editor(h):
    await register_and_book(h, day="Вт, 6 окт", hour="10:00")
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "🗓 Окошки")
    await h.press(ADMIN, "Вт, 6 окт")
    await h.press(ADMIN, "👤 10:00")
    assert "Аня Смирнова" in h.last(ADMIN).text
    await h.press(ADMIN, "← К окошкам дня")
    assert "Вторник, 6 октября" in h.last(ADMIN).text


async def test_anonymous_question_round_trip(h):
    await h.send(STUDENT, "/start")
    await h.press(STUDENT, "Спросить анонимно")
    await h.send(STUDENT, "Мне тревожно перед контрольными, что делать?")
    assert "Вопрос отправлен" in h.last(STUDENT).text

    notice = h.last(ADMIN)
    assert "тревожно перед контрольными" in notice.text
    assert "Аня" not in notice.text and "501" not in notice.text and "anya" not in notice.text

    await h.press(ADMIN, "✍️ Ответить")
    await h.send(ADMIN, "Приходи поговорить, разберём по шагам.")
    assert "Ответ отправлен." in [m.text for m in h.chat(ADMIN)]

    answer = h.last(STUDENT).text
    assert "Ответ психолога" in answer and "разберём по шагам" in answer and "тревожно" in answer

    # второй раз ответить нельзя: старая кнопка «Отмена» под подсказкой ведёт к уже закрытому вопросу
    prompt, _ = h.find_button(ADMIN, "Отмена")
    await h.press(ADMIN, "Отмена")
    assert "Ответ уже отправлен" in prompt.text
    assert "✍️ Ответить" not in [b.text for b in prompt.buttons]


async def test_ban_stops_questions_but_not_booking(h):
    await h.send(STUDENT, "/ask")
    await h.send(STUDENT, "спам спам спам")
    await h.press(ADMIN, "Открыть")
    await h.press(ADMIN, "Запретить автору писать")
    await h.press(ADMIN, "Да, запретить")
    assert (await h.repo.get_user(STUDENT)).is_banned

    await h.send(STUDENT, "/ask")
    assert "Отправлять анонимные вопросы тебе нельзя" in h.last(STUDENT).text
    await register_and_book(h)
    assert "Запись готова" in h.last(STUDENT).text


async def test_question_limit(h):
    for i in range(h.config.questions_per_day):
        await h.send(STUDENT, "/ask")
        await h.send(STUDENT, f"Вопрос номер {i}")
    await h.send(STUDENT, "/ask")
    assert "Новый можно будет задать завтра" in h.last(STUDENT).text


async def test_commands_work_inside_text_input(h):
    await h.send(STUDENT, "/ask")
    await h.send(STUDENT, "/my")
    assert "Мои записи" in h.last(STUDENT).text
    assert await h.repo.new_questions() == []


async def test_photo_instead_of_text(h):
    from aiogram.types import Chat, Message, PhotoSize, Update

    await h.send(STUDENT, "/ask")
    message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=STUDENT, type="private"), from_user=h.users[STUDENT],
        photo=[PhotoSize(file_id="p", file_unique_id="p", width=1, height=1)],
    )
    await h.dp.feed_update(h.bot, Update(update_id=10_000, message=message))
    assert h.last(STUDENT).text == "Сюда можно отправить только текст."


async def test_random_text_shows_menu(h):
    await h.send(STUDENT, "мне очень плохо")
    text = h.last(STUDENT).text
    assert "психолог не увидит" in text and "Нужна помощь" in text
    assert "Записаться" in h.last(STUDENT).buttons[0].text
    assert h.chat(ADMIN) == []


async def test_topic_button_after_restart_keeps_its_slot(h):
    await h.send(STUDENT, "/start")
    await h.press(STUDENT, "Записаться на встречу")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "10:00")
    h.dp.fsm.storage = MemoryStorage()  # «перезапуск бота»: состояние потеряно
    await h.press(STUDENT, "Семья")
    await h.send(STUDENT, "Аня Смирнова")
    await h.send(STUDENT, "8Б")
    assert "10:00–10:45" in h.last(STUDENT).text and "Семья" in h.last(STUDENT).text


async def test_confirm_button_after_restart_is_stale(h):
    await register_and_book(h, hour="10:00")
    await h.press(STUDENT, "← В меню")
    await h.press(STUDENT, "Записаться на встречу")
    await h.press(STUDENT, "Сегодня")
    await h.press(STUDENT, "11:00")
    await h.press(STUDENT, "Семья")
    h.dp.fsm.storage = MemoryStorage()
    await h.press(STUDENT, "✅ Записаться")
    assert h.last_alert == "Эта кнопка устарела. Начни заново из меню."
    assert len(await h.repo.upcoming_for_user(STUDENT, h.clock.now())) == 1


async def test_journal_export(h):
    await register_and_book(h, hour="10:00")
    await register_and_book(h, user_id=OTHER, hour="11:00", name="Петя Иванов", klass="9в")
    await h.send(ADMIN, "/admin")
    await h.press(ADMIN, "📄 Журнал")
    assert "Октябрь 2026: 2 встречи" in h.last(ADMIN).text
    await h.press(ADMIN, "Октябрь 2026")
    document = h.last(ADMIN)
    assert document.document == "journal-2026-10.csv"
    rows = list(csv.reader(io.StringIO(document.document_bytes.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][:3] == ["Дата", "Время", "Ученик"]
    assert rows[1][:4] == ["05.10.2026", "10:00", "Аня Смирнова", "8Б"]
    assert rows[2][2:4] == ["Петя Иванов", "9В"] and len(rows) == 3


async def test_csv_formula_is_escaped():
    from bot.handlers.admin.journal import cell

    assert cell("=1+1") == "'=1+1"
    assert cell("Аня") == "Аня"


async def test_days_beyond_horizon_hidden(h):
    await h.send(STUDENT, "/book")
    labels = [b.text for b in h.last(STUDENT).buttons]
    last_day = h.clock.now().date() + timedelta(days=h.config.booking_days_ahead)
    assert all("20 окт" not in label for label in labels)
    assert last_day.day == 19 and any("19 окт" in label for label in labels)
