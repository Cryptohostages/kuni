from datetime import date, datetime, time

import pytest

from bot.timeutil import day_long, grid_times, when_phrase, when_short, work_days_text
from bot.ui import plural
from bot.validators import normalize_class, normalize_name, parse_time
from conftest import make_config


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("аня смирнова", "Аня Смирнова"),
        ("  Анна-Мария   Петрова ", "Анна-Мария Петрова"),
        ("ИВАН ПЕТРОВ", "Иван Петров"),
        ("Jane Doe", "Jane Doe"),
        ("Я", None),
        ("123", None),
        ("Аня <b>", None),
        ("а" * 61, None),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8б", "8Б"),
        ("10 А", "10А"),
        ("11-в", "11В"),
        ("9 класс", "9"),
        ("9Б класс", "9Б"),
        ("7 кл", "7"),
        ("10-1", "10-1"),
        ("Родитель", "родитель"),
        ("педагог", "учитель"),
        ("8 «Б»", "8Б"),
        ('8"Б"', "8Б"),
        ("12", None),
        ("100", None),
        ("12А", None),
        ("0", None),
        ("абв", None),
        ("", None),
    ],
)
def test_normalize_class(raw, expected):
    assert normalize_class(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("15:30", time(15, 30)), ("9.05", time(9, 5)), ("0930", time(9, 30)), ("24:00", None), ("abc", None)],
)
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_plural():
    forms = ("запись", "записи", "записей")
    assert [plural(n, *forms) for n in (1, 2, 5, 11, 12, 21, 22, 25, 111)] == [
        "запись", "записи", "записей", "записей", "записей", "запись", "записи", "записей", "записей",
    ]


def test_grid_default():
    assert [t.strftime("%H:%M") for t in grid_times(make_config())] == [
        "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00",
    ]


def test_grid_custom():
    config = make_config(day_start="13:00", day_end="15:00", slot_minutes=40, break_minutes=10)
    assert [t.strftime("%H:%M") for t in grid_times(config)] == ["13:00", "13:50"]


def test_config_parses_env_style_values():
    config = make_config(admin_ids="1, 2;3", work_days="1,3,5", digest_time="", day_start="9:00",
                         log_level="info", remind_minutes_before="")
    assert config.admin_ids == [1, 2, 3]
    assert config.work_days == [1, 3, 5]
    assert config.digest_time is None
    assert config.day_start == time(9, 0)
    assert config.log_level == "INFO"
    assert config.remind_minutes_before == 0


@pytest.mark.parametrize(
    "bad",
    [dict(work_days="0,8"), dict(slot_minutes=0), dict(day_start="18:00"), dict(day_start="25:00"),
     dict(log_level="loud"), dict(bot_token=" ")],
)
def test_config_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        make_config(**bad)


def test_dates_in_russian():
    today = date(2026, 10, 5)
    assert day_long(date(2026, 10, 7)) == "среда, 7 октября"
    assert when_short(datetime(2026, 10, 6, 10), today) == "завтра, 10:00"
    assert when_short(datetime(2026, 10, 9, 10), today) == "Пт, 9 окт, 10:00"
    assert when_phrase(datetime(2026, 10, 7, 10), today) == "в среду, 7 октября, в 10:00"
    assert work_days_text([1, 2, 3, 4, 5]) == "Пн–Пт"
    assert work_days_text([1, 3]) == "Пн, Ср"
