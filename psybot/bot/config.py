from datetime import time
from functools import cached_property
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки берутся из .env (см. .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    admin_ids: Annotated[list[int], NoDecode] = []

    school_name: str = "Лицей № 1533 (ЛИТ)"
    psychologist_name: str = ""
    psychologist_room: str = ""

    timezone: str = "Europe/Moscow"
    work_days: Annotated[list[int], NoDecode] = [1, 2, 3, 4, 5]
    day_start: time = time(9, 0)
    day_end: time = time(17, 0)
    slot_minutes: int = 45
    break_minutes: int = 15
    auto_open: bool = True

    booking_days_ahead: int = 14
    min_lead_minutes: int = 60
    max_active_bookings: int = 2

    remind_day_before: bool = True
    remind_minutes_before: int = 60
    digest_time: time | None = time(8, 0)

    questions_per_day: int = 5

    db_path: Path = Path("data/bot.sqlite3")
    proxy_url: str | None = None
    log_level: str = "INFO"

    @field_validator("bot_token")
    @classmethod
    def _token_set(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("BOT_TOKEN пустой: впиши токен от @BotFather в .env")
        return value

    @field_validator("admin_ids", "work_days", mode="before")
    @classmethod
    def _split_ints(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("work_days")
    @classmethod
    def _check_days(cls, value: list[int]) -> list[int]:
        if any(day not in range(1, 8) for day in value):
            raise ValueError("WORK_DAYS: дни недели от 1 (пн) до 7 (вс)")
        return sorted(set(value))

    @field_validator("digest_time", "proxy_url", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def admin_days_ahead(self) -> int:
        # психологу видно чуть дальше, чем ученикам, чтобы заранее закрыть каникулы
        return max(self.booking_days_ahead, 28)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
