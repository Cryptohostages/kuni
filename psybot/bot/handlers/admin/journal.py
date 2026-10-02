"""Журнал консультаций: статистика за месяц и выгрузка в CSV."""

import csv
import io
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens
from ...callbacks import Admin, AdmExport
from ...db import Booking, Repo
from ...timeutil import Clock, hm, month_title
from ...ui import show

router = Router(name="admin_journal")

MONTHS_BACK = 4


def recent_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    result = []
    for _ in range(count):
        result.append((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return result


def cell(value: str) -> str:
    # Excel выполняет ячейки, начинающиеся с =, +, -, @, как формулы
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def to_csv(bookings: list[Booking], now: datetime) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Дата", "Время", "Ученик", "Класс", "Тема", "Комментарий", "Статус", "Причина отмены",
                     "Записались"])
    for b in bookings:
        writer.writerow([
            b.starts_at.strftime("%d.%m.%Y"),
            hm(b.starts_at),
            cell(b.user.full_name or b.user.tg_name),
            b.user.class_name or "",
            admin_screens.topic_label(b.topic) or "",
            cell(b.comment or ""),
            admin_screens.status_label(b, now),
            cell(b.cancel_reason or ""),
            b.created_at.strftime("%d.%m.%Y %H:%M"),
        ])
    # BOM, чтобы Excel сразу понял кириллицу
    return out.getvalue().encode("utf-8-sig")


@router.callback_query(Admin.filter(F.to == "journal"))
async def journal(callback: CallbackQuery, state: FSMContext, repo: Repo, clock: Clock) -> None:
    await state.clear()
    now = clock.now()
    months = recent_months(now.year, now.month, MONTHS_BACK)
    bookings = await repo.month_bookings(*months[0])
    await show(callback, admin_screens.journal(months, bookings, now))


@router.callback_query(AdmExport.filter())
async def export(callback: CallbackQuery, callback_data: AdmExport, callback_answer: CallbackAnswer,
                 repo: Repo, clock: Clock) -> None:
    year, month = int(callback_data.ym[:4]), int(callback_data.ym[4:])
    bookings = await repo.month_bookings(year, month)
    if not bookings:
        callback_answer.text = "За этот месяц записей нет"
        return
    now = clock.now()
    document = BufferedInputFile(to_csv(bookings, now), filename=f"journal-{year}-{month:02d}.csv")
    caption = f"Журнал за {month_title(year, month).lower()}. Выгружен {now:%d.%m.%Y %H:%M}"
    if isinstance(callback.message, Message):
        await callback.message.answer_document(document, caption=caption)
