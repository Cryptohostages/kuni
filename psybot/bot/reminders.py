"""Когда ученику приходят напоминания. Нужны и планировщику, и экрану «Запись готова»."""

from datetime import timedelta

from .config import Settings
from .db import Booking

DAY_BEFORE = timedelta(hours=24)
# если запись сделана совсем незадолго до напоминания за день, его не шлём: ученик и так помнит
FRESH_BOOKING = timedelta(hours=2)


def soon_delta(cfg: Settings) -> timedelta:
    return timedelta(minutes=cfg.remind_minutes_before)


def will_remind_day(booking: Booking, cfg: Settings) -> bool:
    return cfg.remind_day_before and booking.starts_at - booking.created_at >= DAY_BEFORE + FRESH_BOOKING


def will_remind_soon(booking: Booking, cfg: Settings) -> bool:
    return cfg.remind_minutes_before > 0 and booking.starts_at - booking.created_at >= soon_delta(cfg)
