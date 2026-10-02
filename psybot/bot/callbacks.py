"""Данные inline-кнопок. Префиксы короткие: в callback_data влезает только 64 байта."""

from aiogram.filters.callback_data import CallbackData


class Menu(CallbackData, prefix="m"):
    to: str  # home | book | my | ask | about | help | profile
    new: bool = False  # открыть экран новым сообщением, а не поверх этого (например, под ответом психолога)


class BookDay(CallbackData, prefix="bd"):
    day: str  # YYYYMMDD


class BookSlot(CallbackData, prefix="bs"):
    id: int


class BookTopic(CallbackData, prefix="bt"):
    code: str
    slot: int


class BookConfirm(CallbackData, prefix="bc"):
    action: str  # ok | comment | skip | clear | back
    slot: int


class MyBooking(CallbackData, prefix="mb"):
    id: int
    action: str  # view | cancel | cancel_yes | keep


class Admin(CallbackData, prefix="a"):
    to: str  # home | records | slots | questions | journal


class AdmRecords(CallbackData, prefix="ar"):
    span: str  # today | tomorrow | week


class AdmWeek(CallbackData, prefix="aw"):
    week: int  # 0 — текущая неделя, 1 — следующая...


class AdmDay(CallbackData, prefix="ad"):
    day: str
    action: str = "view"  # view | open_all | close_day | custom


class AdmSlot(CallbackData, prefix="as"):
    day: str
    hm: str  # HHMM
    to: str  # open | close | view: что должно получиться, чтобы двойное нажатие не отменяло само себя


class AdmBooking(CallbackData, prefix="ab"):
    id: int
    action: str  # view | cancel | no_reason | done | missed
    back: str = "today"  # куда вернуться: today | tomorrow | week | dYYYYMMDD


class AdmQuestion(CallbackData, prefix="aq"):
    id: int
    action: str  # view | reply | hide | ban | ban_yes


class AdmExport(CallbackData, prefix="ae"):
    ym: str  # YYYYMM
