"""Экраны кабинета психолога."""

from datetime import date, datetime, time, timedelta

from aiogram.types import InlineKeyboardButton

from . import texts
from .callbacks import Admin, AdmBooking, AdmDay, AdmExport, AdmQuestion, AdmRecords, AdmSlot, AdmWeek, Menu
from .db import Booking, DaySlot, Question, Status
from .timeutil import (
    day_key,
    day_long,
    day_month,
    day_short,
    day_title,
    hm,
    month_title,
    time_range,
    when_phrase,
    when_short,
)
from .ui import DANGER, PRIMARY, SUCCESS, Screen, btn, cap, chunks, esc, kb, plural, short

TO_PANEL = btn("← Кабинет", Admin(to="home"))

STATUS_LABEL = {
    Status.ACTIVE: "ждём встречи",
    Status.DONE: "встреча состоялась",
    Status.MISSED: "неявка",
    Status.CANCELLED: "отменена учеником",
    Status.CANCELLED_ADMIN: "отменена психологом",
}

STATUS_MARK = {Status.DONE: "✓ ", Status.MISSED: "✗ "}


def topic_label(topic: str | None) -> str | None:
    if not topic or topic == "skip":
        return None
    return texts.TOPICS.get(topic, topic)


def student_link(b: Booking) -> str:
    name = esc(b.user.full_name or b.user.tg_name or "без имени")
    text = f'<a href="tg://user?id={b.user.id}">{name}</a>'
    if b.user.class_name:
        text += f", {esc(b.user.class_name)}"
    if b.user.username:
        text += f" · @{esc(b.user.username)}"
    return text


def panel(today: date, today_bookings: list[Booking], now: datetime, new_questions: int) -> Screen:
    lines = ["<b>Кабинет психолога</b>", f"Сегодня {day_long(today)}", ""]
    n = len(today_bookings)
    if n:
        line = f"Записей сегодня: <b>{n}</b>"
        upcoming = [b for b in today_bookings if b.starts_at >= now and b.status == Status.ACTIVE]
        if upcoming:
            line += f", ближайшая в {hm(upcoming[0].starts_at)}"
        lines.append(line)
    else:
        lines.append("Сегодня записей нет")
    lines.append(f"Новых вопросов: <b>{new_questions}</b>" if new_questions else "Новых вопросов нет")
    questions_label = f"✉️ Вопросы · {new_questions}" if new_questions else "✉️ Вопросы"
    return Screen(
        "\n".join(lines),
        kb(
            [btn("📋 Записи", AdmRecords(span="today"), PRIMARY), btn("🗓 Окошки", AdmWeek(week=0), PRIMARY)],
            [btn(questions_label, Admin(to="questions")), btn("📄 Журнал", Admin(to="journal"))],
            btn("← Меню бота", Menu(to="home")),
        ),
    )


# --- записи ----------------------------------------------------------------------

SPANS = {"today": "Сегодня", "tomorrow": "Завтра", "week": "Неделя"}


def records(span: str, bookings: list[Booking], today: date) -> Screen:
    if span == "today":
        title = f"Записи на сегодня, {day_long(today)}"
    elif span == "tomorrow":
        title = f"Записи на завтра, {day_long(today + timedelta(days=1))}"
    else:
        title = "Записи на 7 дней"
    lines = [f"<b>{title}</b>", ""]
    buttons = []
    current_day = None
    for b in bookings:
        if span == "week" and b.starts_at.date() != current_day:
            current_day = b.starts_at.date()
            if len(lines) > 2:
                lines.append("")
            lines.append(f"<b>{cap(day_short(current_day))}</b>")
        mark = STATUS_MARK.get(b.status, "")
        line = f"{mark}{hm(b.starts_at)}  {esc(b.user.display)}"
        if topic := topic_label(b.topic):
            line += f" · <i>{esc(topic.lower())}</i>"
        lines.append(line)
        label = f"{mark}{hm(b.starts_at)} · {b.user.display}"
        if span == "week":
            label = f"{day_short(b.starts_at.date())}, {label}"
        buttons.append(btn(short(label, 40), AdmBooking(id=b.id, action="view", back=span)))
    if not bookings:
        lines.append("Записей нет.")
    elif any(b.status != Status.ACTIVE for b in bookings):
        lines += ["", "<i>✓ встреча состоялась, ✗ неявка</i>"]
    tabs = [
        btn(("• " if key == span else "") + label, AdmRecords(span=key), PRIMARY if key == span else None)
        for key, label in SPANS.items()
    ]
    return Screen("\n".join(lines), kb(tabs, *buttons[:60], TO_PANEL))


def booking(b: Booking, now: datetime, back: str) -> Screen:
    lines = [
        f"<b>Запись #{b.id}</b>",
        "",
        f"👤 {student_link(b)}",
        f"🗓 {day_title(b.starts_at.date())}, {time_range(b.starts_at, b.minutes)}",
    ]
    if topic := topic_label(b.topic):
        lines.append(f"💬 {esc(topic)}")
    if b.comment:
        lines.append(f"📝 <i>{esc(b.comment)}</i>")
    lines += ["", f"Статус: <b>{STATUS_LABEL[b.status]}</b>"]
    if b.status in (Status.CANCELLED, Status.CANCELLED_ADMIN) and b.cancel_reason:
        lines.append(f"Причина: {esc(b.cancel_reason)}")
    lines.append(f"<i>Записались {when_short(b.created_at, now.date())}</i>")

    rows = []
    started = b.starts_at <= now
    if b.status == Status.ACTIVE and not started:
        rows.append(btn("Отменить запись", AdmBooking(id=b.id, action="cancel", back=back), DANGER))
    if started and b.status in (Status.ACTIVE, Status.DONE, Status.MISSED):
        rows.append(
            [
                btn("✓ Состоялась", AdmBooking(id=b.id, action="done", back=back),
                    SUCCESS if b.status == Status.DONE else None),
                btn("✗ Неявка", AdmBooking(id=b.id, action="missed", back=back),
                    DANGER if b.status == Status.MISSED else None),
            ]
        )
    rows.append(back_button(back))
    return Screen("\n".join(lines), kb(*rows))


def back_button(back: str) -> InlineKeyboardButton:
    if back.startswith("d"):
        return btn("← К окошкам дня", AdmDay(day=back[1:]))
    if back == "q":
        return TO_PANEL
    return btn("← К записям", AdmRecords(span=back if back in SPANS else "today"))


def cancel_reason_prompt(b: Booking, today: date, back: str) -> Screen:
    return Screen(
        f"Отменяем запись: {esc(b.user.display)}, {when_phrase(b.starts_at, today)}.\n\n"
        "Напиши причину одним сообщением, её получит ученик. Или отмени без объяснений.",
        kb(
            btn("Отменить без причины", AdmBooking(id=b.id, action="no_reason", back=back), DANGER),
            btn("Не отменять", AdmBooking(id=b.id, action="view", back=back)),
        ),
    )


# --- окошки ----------------------------------------------------------------------


def week(week_no: int, days: list[date], overview: dict[date, tuple[int, int]], work_days: set[int],
         today: date, max_week: int) -> Screen:
    first, last = days[0], days[-1]
    if first.month == last.month:
        period = f"{first.day}–{day_month(last)}"
    else:
        period = f"{day_month(first)} – {day_month(last)}"
    rows = []
    for d in days:
        free, booked = overview.get(d, (0, 0))
        label = "Сегодня" if d == today else day_short(d)
        if free or booked:
            parts = []
            if free:
                parts.append(f"🟢 {free}")
            if booked:
                parts.append(f"👤 {booked}")
            label += " · " + "  ".join(parts)
        elif d.isoweekday() in work_days:
            label += " · закрыто"
        else:
            label += " · выходной"
        rows.append(btn(label, AdmDay(day=day_key(d))))
    nav = []
    if week_no > 0:
        nav.append(btn("‹ Раньше", AdmWeek(week=week_no - 1)))
    if week_no < max_week:
        nav.append(btn("Дальше ›", AdmWeek(week=week_no + 1)))
    return Screen(
        f"<b>Окошки · {period}</b>\n\n"
        "Выбери день, чтобы открыть или закрыть время.\n"
        "🟢 свободные окошки, 👤 записи",
        kb(*rows, nav, TO_PANEL),
    )


def day_editor(day: date, items: list[DaySlot], grid: list[time], now: datetime, week_no: int) -> Screen:
    by_time = {i.slot.starts_at.time(): i for i in items}
    times = sorted(set(grid) | set(by_time))
    buttons = []
    for t in times:
        starts = datetime.combine(day, t)
        item = by_time.get(t)
        cb = AdmSlot(day=day_key(day), hm=t.strftime("%H%M"))
        if item and item.booking:
            mark = STATUS_MARK.get(item.booking.status, "👤 ")
            buttons.append(btn(f"{mark}{hm(t)}", cb, PRIMARY))
        elif starts < now:
            continue
        elif item and item.slot.is_open:
            buttons.append(btn(f"🟢 {hm(t)}", cb, SUCCESS))
        else:
            buttons.append(btn(f"▫️ {hm(t)}", cb))
    text = (
        f"<b>{day_title(day)}</b>\n\n"
        "🟢 свободно — нажми, чтобы закрыть\n"
        "▫️ закрыто — нажми, чтобы открыть\n"
        "👤 запись — нажми, чтобы посмотреть"
    )
    if not buttons:
        text = f"<b>{day_title(day)}</b>\n\nНа этот день времени больше нет."
    actions = []
    if any(b.text.startswith("▫️") for b in buttons):
        actions.append(btn("Открыть всё", AdmDay(day=day_key(day), action="open_all")))
    if any(b.text.startswith("🟢") for b in buttons):
        actions.append(btn("Закрыть свободные", AdmDay(day=day_key(day), action="close_free")))
    return Screen(
        text,
        kb(
            *chunks(buttons, 3),
            actions,
            btn("＋ Другое время", AdmDay(day=day_key(day), action="custom")),
            btn("← К неделе", AdmWeek(week=week_no)),
        ),
    )


def custom_time_prompt(day: date) -> Screen:
    return Screen(
        f"Во сколько открыть окошко {day_month(day)}? Напиши время, например <i>15:30</i>.",
        kb(btn("Отмена", AdmDay(day=day_key(day)))),
    )


# --- вопросы ---------------------------------------------------------------------


def questions(items: list[Question]) -> Screen:
    if not items:
        return Screen("<b>Анонимные вопросы</b>\n\nНовых вопросов нет.", kb(TO_PANEL))
    rows = [btn(f"#{q.id} · {short(q.text, 32)}", AdmQuestion(id=q.id, action="view")) for q in items[:40]]
    n = len(items)
    return Screen(
        f"<b>Анонимные вопросы</b>\n\n{n} {plural(n, 'новый вопрос', 'новых вопроса', 'новых вопросов')} без ответа.",
        kb(*rows, TO_PANEL),
    )


def question(q: Question, today: date) -> Screen:
    text = (
        f"<b>Вопрос #{q.id}</b> · {when_short(q.created_at, today)}\n\n"
        f"<blockquote>{esc(q.text)}</blockquote>\n\n"
        "<i>Автор анонимен. Ответ придёт ему в бот.</i>"
    )
    if q.status != "new":
        text += "\n\n" + ("Ответ уже отправлен." if q.status == "answered" else "Вопрос скрыт.")
        return Screen(text, kb(btn("← К вопросам", Admin(to="questions"))))
    return Screen(
        text,
        kb(
            [
                btn("✍️ Ответить", AdmQuestion(id=q.id, action="reply"), PRIMARY),
                btn("Скрыть", AdmQuestion(id=q.id, action="hide")),
            ],
            btn("🚫 Запретить автору писать", AdmQuestion(id=q.id, action="ban")),
            btn("← К вопросам", Admin(to="questions")),
        ),
    )


def answer_prompt(q: Question) -> Screen:
    return Screen(
        f"<b>Ответ на вопрос #{q.id}</b>\n\n<blockquote expandable>{esc(q.text)}</blockquote>\n\n"
        "Напиши ответ одним сообщением, бот перешлёт его автору.",
        kb(btn("Отмена", AdmQuestion(id=q.id, action="view"))),
    )


def ban_confirm(q: Question) -> Screen:
    return Screen(
        "Автор этого вопроса больше не сможет отправлять анонимные вопросы, а его новые вопросы скроются. "
        "Записываться на встречи он сможет, как раньше. Кто это, вы так и не узнаете.",
        kb(
            btn("Да, запретить", AdmQuestion(id=q.id, action="ban_yes"), DANGER),
            btn("Отмена", AdmQuestion(id=q.id, action="view")),
        ),
    )


# --- журнал ----------------------------------------------------------------------


def journal(months: list[tuple[int, int]], stats: dict[Status, int]) -> Screen:
    year, month = months[0]
    total = sum(stats.get(s, 0) for s in (Status.ACTIVE, Status.DONE, Status.MISSED))
    cancelled = stats.get(Status.CANCELLED, 0) + stats.get(Status.CANCELLED_ADMIN, 0)
    lines = [
        "<b>Журнал консультаций</b>",
        "",
        f"{month_title(year, month)}: {total} {plural(total, 'встреча', 'встречи', 'встреч')}",
        f"состоялось — {stats.get(Status.DONE, 0)}, неявок — {stats.get(Status.MISSED, 0)}, "
        f"отмен — {cancelled}",
        "",
        "Выгрузка — таблица CSV, открывается в Excel и Google Таблицах.",
    ]
    buttons = [btn(month_title(y, m), AdmExport(ym=f"{y:04d}{m:02d}")) for y, m in months]
    return Screen("\n".join(lines), kb(*chunks(buttons, 2), TO_PANEL))


# --- уведомления психологу -------------------------------------------------------


def notify_booked(b: Booking, today: date) -> Screen:
    lines = ["🗓 <b>Новая запись</b>", "", f"<b>{cap(when_short(b.starts_at, today))}</b>", student_link(b)]
    if topic := topic_label(b.topic):
        lines.append(f"💬 {esc(topic)}")
    if b.comment:
        lines.append(f"📝 <i>{esc(b.comment)}</i>")
    return Screen("\n".join(lines), kb(btn("Открыть запись", AdmBooking(id=b.id, action="view", back="week"))))


def notify_cancelled(b: Booking, today: date) -> Screen:
    return Screen(
        f"↩️ <b>Запись отменена учеником</b>\n\n{cap(when_short(b.starts_at, today))} · {esc(b.user.display)}\n"
        "Это время снова свободно."
    )


def notify_question(q: Question) -> Screen:
    return Screen(
        f"✉️ <b>Новый анонимный вопрос #{q.id}</b>\n\n<blockquote>{esc(q.text)}</blockquote>",
        kb(
            btn("✍️ Ответить", AdmQuestion(id=q.id, action="reply"), PRIMARY),
            btn("Открыть", AdmQuestion(id=q.id, action="view")),
        ),
    )


def digest(today: date, bookings: list[Booking]) -> Screen:
    n = len(bookings)
    lines = [f"☀️ <b>Сегодня {n} {plural(n, 'встреча', 'встречи', 'встреч')}</b>", day_title(today), ""]
    for b in bookings:
        line = f"{hm(b.starts_at)}  {esc(b.user.display)}"
        if topic := topic_label(b.topic):
            line += f" · <i>{esc(topic.lower())}</i>"
        lines.append(line)
    return Screen("\n".join(lines), kb(btn("📋 Открыть записи", AdmRecords(span="today"))))
