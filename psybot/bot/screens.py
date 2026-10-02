"""Экраны для учеников: текст + кнопки. Обработчики только решают, какой экран показать."""

from datetime import date, datetime

from . import texts
from .callbacks import Admin, BookConfirm, BookDay, BookSlot, BookTopic, Menu, MyBooking
from .config import Settings
from .db import Booking, Slot, User
from .reminders import will_remind_day, will_remind_soon
from .timeutil import (
    day_key,
    day_short,
    day_title,
    hm,
    time_range,
    when_phrase,
    when_short,
    work_days_text,
)
from .ui import DANGER, PRIMARY, SUCCESS, Screen, btn, cap, chunks, esc, kb, plural

TO_MENU = btn("← В меню", Menu(to="home"))


def place(cfg: Settings) -> str:
    return esc(cfg.psychologist_room)


def home(first_name: str, upcoming: Booking | None, today: date, cfg: Settings, is_admin: bool) -> Screen:
    text = f"<b>Привет, {esc(first_name)}!</b>\n\n{texts.HOME}"
    if upcoming:
        where = f" · {place(cfg)}" if cfg.psychologist_room else ""
        text += f"\n\n📌 Ближайшая встреча: <b>{when_short(upcoming.starts_at, today)}</b>{where}"
    rows = [
        btn("🗓 Записаться на встречу", Menu(to="book"), PRIMARY),
        [btn("📌 Мои записи", Menu(to="my")), btn("✉️ Спросить анонимно", Menu(to="ask"))],
        [btn("👤 О психологе", Menu(to="about")), btn("🆘 Нужна помощь", Menu(to="help"), DANGER)],
    ]
    if is_admin:
        rows.append(btn("🔑 Кабинет психолога", Admin(to="home")))
    return Screen(text, kb(*rows))


def about(cfg: Settings) -> Screen:
    title = esc(cfg.psychologist_name) if cfg.psychologist_name else "Школьный психолог"
    lines = [f"<b>{title}</b>"]
    if cfg.psychologist_name:
        lines.append(f"Педагог-психолог, {esc(cfg.school_name)}")
    else:
        lines.append(esc(cfg.school_name))
    lines.append("")
    if cfg.psychologist_room:
        lines.append(f"📍 {place(cfg)}")
    lines.append(f"🕙 По записи: {work_days_text(cfg.work_days)}, {hm(cfg.day_start)}–{hm(cfg.day_end)}")
    lines += ["", texts.ABOUT_TOPICS, "", texts.ABOUT_PRIVACY]
    return Screen(
        "\n".join(lines),
        kb(btn("🗓 Записаться на встречу", Menu(to="book"), PRIMARY), TO_MENU),
    )


def sos() -> Screen:
    return Screen(texts.SOS, kb(btn("✉️ Написать психологу анонимно", Menu(to="ask")), TO_MENU))


# --- запись ----------------------------------------------------------------------


def book_days(days: list[tuple[date, int]], today: date) -> Screen:
    if not days:
        return Screen(
            "<b>Свободных окошек сейчас нет</b>\n\n"
            "Психолог открывает новое время по ходу недели, загляни через пару дней. "
            "Если вопрос не ждёт, задай его анонимно: ответ придёт сюда.",
            kb(btn("✉️ Спросить анонимно", Menu(to="ask")), TO_MENU),
        )
    buttons = []
    for d, free in days:
        label = day_short(d)
        if d == today:
            label = "Сегодня"
        buttons.append(btn(f"{label} · {free}", BookDay(day=day_key(d))))
    return Screen(
        "<b>Запись к психологу</b>\n\nВыбери день. Цифра на кнопке — сколько свободных окошек.",
        kb(*chunks(buttons, 2), TO_MENU),
    )


def book_limit(n: int) -> Screen:
    return Screen(
        f"<b>У тебя уже {n} {plural(n, 'запись', 'записи', 'записей')}</b>\n\n"
        "Новую можно будет сделать после встречи. Или отмени одну из текущих, если планы поменялись.",
        kb(btn("📌 Мои записи", Menu(to="my"), PRIMARY), TO_MENU),
    )


def book_slots(day: date, slots: list[Slot], cfg: Settings) -> Screen:
    back = btn("← Другой день", Menu(to="book"))
    if not slots:
        return Screen(
            f"<b>{day_title(day)}</b>\n\nНа этот день свободного времени уже не осталось.",
            kb(back),
        )
    buttons = [btn(hm(s.starts_at), BookSlot(id=s.id)) for s in slots]
    return Screen(
        f"<b>{day_title(day)}</b>\n\nВыбери время. Встреча длится {cfg.slot_minutes} минут.",
        kb(*chunks(buttons, 3), back),
    )


def book_topic(slot: Slot, today: date) -> Screen:
    buttons = [btn(label, BookTopic(code=code)) for code, label in texts.TOPICS.items()]
    return Screen(
        f"<b>{cap(when_short(slot.starts_at, today))}</b>\n\n"
        "О чём хочется поговорить? Так психологу будет проще подготовиться. Можно и не уточнять.",
        kb(*buttons[:-2], buttons[-2:], btn("← Другое время", BookDay(day=day_key(slot.starts_at.date())))),
    )


def booking_card(starts_at: datetime, minutes: int, cfg: Settings, topic: str | None = None,
                 who: User | None = None) -> list[str]:
    lines = [f"🗓 {day_title(starts_at.date())}", f"🕙 {time_range(starts_at, minutes)}"]
    if cfg.psychologist_room:
        lines.append(f"📍 {place(cfg)}")
    if who:
        lines.append(f"👤 {esc(who.full_name)}, {esc(who.class_name)}")
    if topic and topic != "skip":
        lines.append(f"💬 {texts.TOPICS.get(topic, esc(topic))}")
    return lines


def book_confirm(slot: Slot, user: User, topic: str | None, comment: str | None, cfg: Settings) -> Screen:
    lines = ["<b>Проверь, всё ли верно</b>", "", *booking_card(slot.starts_at, slot.minutes, cfg, topic, user)]
    if comment:
        lines.append(f"📝 <i>{esc(comment)}</i>")
    return Screen(
        "\n".join(lines),
        kb(
            btn("✅ Записаться", BookConfirm(action="ok"), SUCCESS),
            [
                btn("✏️ Изменить комментарий" if comment else "✏️ Комментарий", BookConfirm(action="comment")),
                btn("👤 Имя и класс", Menu(to="profile")),
            ],
            btn("← Назад", BookConfirm(action="back")),
        ),
    )


def comment_prompt() -> Screen:
    return Screen(texts.COMMENT_PROMPT, kb(btn("Пропустить", BookConfirm(action="skip"))))


def reminders_promise(booking: Booking, cfg: Settings) -> str:
    parts = []
    if will_remind_day(booking, cfg):
        parts.append("за день")
    if will_remind_soon(booking, cfg):
        n = cfg.remind_minutes_before
        if n % 60 == 0:
            hours = n // 60
            parts.append("за час" if hours == 1 else f"за {hours} {plural(hours, 'час', 'часа', 'часов')}")
        else:
            parts.append(f"за {n} {plural(n, 'минуту', 'минуты', 'минут')}")
    if not parts:
        return ""
    return f"Я напомню {' и '.join(parts)} до встречи. "


def booked(booking: Booking, cfg: Settings) -> Screen:
    card = booking_card(booking.starts_at, booking.minutes, cfg)
    return Screen(
        "<b>Запись готова</b>\n\n"
        + "\n".join(card)
        + "\n\n"
        + reminders_promise(booking, cfg)
        + "Если планы поменяются, отмени запись в «Мои записи», чтобы время досталось кому-то ещё.",
        kb(btn("📌 Мои записи", Menu(to="my")), TO_MENU),
    )


# --- мои записи ------------------------------------------------------------------


def my_bookings(bookings: list[Booking], user: User, today: date, cfg: Settings) -> Screen:
    lines = ["<b>Мои записи</b>", ""]
    rows = []
    if bookings:
        for b in bookings:
            line = f"• <b>{when_short(b.starts_at, today)}</b>"
            if b.topic and b.topic != "skip":
                line += f" · {texts.TOPICS.get(b.topic, '').lower()}"
            lines.append(line)
            rows.append(btn(f"{when_short(b.starts_at, today)}", MyBooking(id=b.id, action="view")))
        lines += ["", "Нажми на запись, чтобы посмотреть подробности или отменить."]
    else:
        lines.append("Пока записей нет.")
        rows.append(btn("🗓 Записаться на встречу", Menu(to="book"), PRIMARY))
    if user.has_profile:
        lines += ["", f"<i>Записываю как: {esc(user.full_name)}, {esc(user.class_name)}</i>"]
        rows.append(btn("✏️ Изменить имя и класс", Menu(to="profile")))
    rows.append(TO_MENU)
    return Screen("\n".join(lines), kb(*rows))


def my_booking(booking: Booking, cfg: Settings) -> Screen:
    lines = ["<b>Встреча с психологом</b>", "", *booking_card(booking.starts_at, booking.minutes, cfg, booking.topic)]
    if booking.comment:
        lines.append(f"📝 <i>{esc(booking.comment)}</i>")
    return Screen(
        "\n".join(lines),
        kb(
            btn("Отменить запись", MyBooking(id=booking.id, action="cancel"), DANGER),
            btn("← Мои записи", Menu(to="my")),
        ),
    )


def my_cancel_confirm(booking: Booking, today: date) -> Screen:
    return Screen(
        f"Отменить встречу {when_phrase(booking.starts_at, today)}?",
        kb(
            [
                btn("Да, отменить", MyBooking(id=booking.id, action="cancel_yes"), DANGER),
                btn("Нет, оставить", MyBooking(id=booking.id, action="view")),
            ]
        ),
    )


def my_cancelled() -> Screen:
    return Screen(
        "Запись отменена. Это время снова свободно для других.",
        kb(btn("🗓 Записаться на другое время", Menu(to="book"), PRIMARY), TO_MENU),
    )


# --- анонимные вопросы -----------------------------------------------------------


def ask_prompt() -> Screen:
    return Screen(texts.ASK_PROMPT, kb(btn("Отмена", Menu(to="home"))))


def ask_sent() -> Screen:
    return Screen(
        "<b>Вопрос отправлен</b>\n\nКогда психолог ответит, сообщение придёт в этот чат.",
        kb(TO_MENU),
    )


def ask_limit() -> Screen:
    return Screen(
        "На сегодня вопросов уже много: психолог прочитает их и ответит. Новый можно будет задать завтра.",
        kb(TO_MENU),
    )


def ask_banned() -> Screen:
    return Screen(
        "Отправлять анонимные вопросы тебе сейчас нельзя. Записаться на встречу можно, как и раньше.",
        kb(btn("🗓 Записаться на встречу", Menu(to="book")), TO_MENU),
    )


def answer_to_student(question: str, answer: str) -> Screen:
    return Screen(
        f"<b>Ответ психолога</b>\n\n<blockquote expandable>{esc(question)}</blockquote>\n\n{esc(answer)}",
        kb(
            btn("🗓 Записаться на встречу", Menu(to="book")),
            btn("✉️ Спросить ещё", Menu(to="ask")),
        ),
    )


# --- уведомления ученику ---------------------------------------------------------


def remind_day(booking: Booking, today: date, cfg: Settings) -> Screen:
    where = f", {place(cfg)}" if cfg.psychologist_room else ""
    return Screen(
        f"<b>Напоминание</b>\n\n{cap(when_phrase(booking.starts_at, today))} встреча с психологом{where}.\n\n"
        "Если прийти не получается, отмени запись: время достанется кому-то ещё.",
        kb(
            [
                btn("👌 Приду", MyBooking(id=booking.id, action="keep"), SUCCESS),
                btn("Отменить", MyBooking(id=booking.id, action="cancel")),
            ]
        ),
    )


def remind_soon(booking: Booking, today: date, cfg: Settings) -> Screen:
    where = f", {place(cfg)}" if cfg.psychologist_room else ""
    return Screen(f"Скоро встреча с психологом: {when_phrase(booking.starts_at, today)}{where}.")


def cancelled_by_admin(booking: Booking, reason: str | None, today: date) -> Screen:
    text = f"<b>Встреча отменена</b>\n\nВстречу {when_phrase(booking.starts_at, today)} пришлось отменить."
    if reason:
        text += f"\n\n<blockquote>{esc(reason)}</blockquote>"
    text += "\n\nВыбери другое время, психолог будет ждать."
    return Screen(text, kb(btn("🗓 Выбрать другое время", Menu(to="book"), PRIMARY)))
