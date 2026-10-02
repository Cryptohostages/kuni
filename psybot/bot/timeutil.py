from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import Settings

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WEEKDAYS_ACC = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

DB_FORMAT = "%Y-%m-%d %H:%M"


class Clock:
    """Текущее время в часовом поясе школы. Без tzinfo — так же, как хранится в базе."""

    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz

    def now(self) -> datetime:
        return datetime.now(self.tz).replace(tzinfo=None, second=0, microsecond=0)


def to_db(dt: datetime) -> str:
    return dt.strftime(DB_FORMAT)


def from_db(value: str) -> datetime:
    return datetime.strptime(value, DB_FORMAT)


def day_key(d: date) -> str:
    return d.strftime("%Y%m%d")


def parse_day_key(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def hm(t: time | datetime) -> str:
    return t.strftime("%H:%M")


def day_long(d: date) -> str:
    """понедельник, 6 октября"""
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def day_month(d: date) -> str:
    """6 октября"""
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def day_title(d: date) -> str:
    """Понедельник, 6 октября"""
    return day_long(d).capitalize()


def day_short(d: date) -> str:
    """Пн, 6 окт"""
    return f"{WEEKDAYS_SHORT[d.weekday()]}, {d.day} {MONTHS_SHORT[d.month - 1]}"


def relative_day(d: date, today: date) -> str | None:
    if d == today:
        return "сегодня"
    if d == today + timedelta(days=1):
        return "завтра"
    return None


def when_short(dt: datetime, today: date) -> str:
    """завтра, 10:00 · Пн, 6 окт, 10:00"""
    rel = relative_day(dt.date(), today)
    return f"{rel or day_short(dt.date())}, {hm(dt)}"


def when_phrase(dt: datetime, today: date) -> str:
    """завтра в 10:00 · в понедельник, 6 октября, в 10:00"""
    rel = relative_day(dt.date(), today)
    if rel:
        return f"{rel} в {hm(dt)}"
    d = dt.date()
    return f"в {WEEKDAYS_ACC[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}, в {hm(dt)}"


def time_range(start: datetime, minutes: int) -> str:
    return f"{hm(start)}–{hm(start + timedelta(minutes=minutes))}"


def grid_times(cfg: Settings) -> list[time]:
    """Стандартная сетка окошек на день из настроек."""
    result = []
    cursor = datetime.combine(date.min, cfg.day_start)
    end = datetime.combine(date.min, cfg.day_end)
    step = timedelta(minutes=cfg.slot_minutes + cfg.break_minutes)
    while cursor + timedelta(minutes=cfg.slot_minutes) <= end:
        result.append(cursor.time())
        cursor += step
    return result


def is_work_day(d: date, cfg: Settings) -> bool:
    return d.isoweekday() in cfg.work_days


def work_days_text(days: list[int]) -> str:
    """[1,2,3,4,5] -> Пн–Пт, [1,3,5] -> Пн, Ср, Пт"""
    if not days:
        return ""
    if days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
        return f"{WEEKDAYS_SHORT[days[0] - 1]}–{WEEKDAYS_SHORT[days[-1] - 1]}"
    return ", ".join(WEEKDAYS_SHORT[d - 1] for d in days)


def month_title(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"
