import asyncio
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path

import aiosqlite

from .timeutil import from_db, to_db

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT,
    tg_name     TEXT NOT NULL DEFAULT '',
    full_name   TEXT,
    class_name  TEXT,
    is_banned   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    starts_at  TEXT NOT NULL UNIQUE,
    minutes    INTEGER NOT NULL,
    is_open    INTEGER NOT NULL DEFAULT 1,
    auto       INTEGER NOT NULL DEFAULT 0  -- 1: создано по сетке из настроек, 0: открыто психологом вручную
);

CREATE TABLE IF NOT EXISTS bookings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id        INTEGER NOT NULL REFERENCES slots(id),
    user_id        INTEGER NOT NULL REFERENCES users(id),
    topic          TEXT,
    comment        TEXT,
    status         TEXT NOT NULL DEFAULT 'active',
    cancel_reason  TEXT,
    created_at     TEXT NOT NULL,
    cancelled_at   TEXT,
    reminded_day   INTEGER NOT NULL DEFAULT 0,
    reminded_soon  INTEGER NOT NULL DEFAULT 0
);

-- на одно окошко может быть только одна действующая запись
CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_per_slot ON bookings(slot_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS bookings_by_user ON bookings(user_id, status);

-- user_id нужен, только пока вопрос ждёт ответа; через сутки после ответа связь стирается
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    text         TEXT NOT NULL,
    answer       TEXT,
    status       TEXT NOT NULL DEFAULT 'new',
    created_at   TEXT NOT NULL,
    answered_at  TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class Status(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    MISSED = "missed"
    CANCELLED = "cancelled"
    CANCELLED_ADMIN = "cancelled_admin"


class BookResult(Enum):
    OK = "ok"
    ALREADY = "already"  # этот же человек уже записан на это время (двойное нажатие)
    TAKEN = "taken"
    UNAVAILABLE = "unavailable"
    LIMIT = "limit"
    TOO_OFTEN = "too_often"


@dataclass(slots=True)
class User:
    id: int
    username: str | None
    tg_name: str
    full_name: str | None
    class_name: str | None
    is_banned: bool

    @property
    def has_profile(self) -> bool:
        return bool(self.full_name and self.class_name)

    @property
    def display(self) -> str:
        if self.has_profile:
            return f"{self.full_name}, {self.class_name}"
        return self.tg_name or f"id {self.id}"


@dataclass(slots=True)
class Slot:
    id: int
    starts_at: datetime
    minutes: int
    is_open: bool
    auto: bool


@dataclass(slots=True)
class Booking:
    id: int
    slot_id: int
    starts_at: datetime
    minutes: int
    user: User
    topic: str | None
    comment: str | None
    status: Status
    cancel_reason: str | None
    created_at: datetime
    reminded_day: bool
    reminded_soon: bool


@dataclass(slots=True)
class DaySlot:
    """Окошко в редакторе психолога: само окошко и запись на него, если есть."""

    slot: Slot
    booking: Booking | None


@dataclass(slots=True)
class Question:
    id: int
    user_id: int | None
    text: str
    answer: str | None
    status: str
    created_at: datetime


_BOOKING_SELECT = """
SELECT b.id, b.slot_id, s.starts_at, s.minutes, b.topic, b.comment, b.status, b.cancel_reason,
       b.created_at, b.reminded_day, b.reminded_soon,
       u.id AS u_id, u.username, u.tg_name, u.full_name, u.class_name, u.is_banned
FROM bookings b
JOIN slots s ON s.id = b.slot_id
JOIN users u ON u.id = b.user_id
"""


def _user(row: sqlite3.Row, prefix: str = "") -> User:
    return User(
        id=row[f"{prefix}id"],
        username=row["username"],
        tg_name=row["tg_name"],
        full_name=row["full_name"],
        class_name=row["class_name"],
        is_banned=bool(row["is_banned"]),
    )


def _slot(row: sqlite3.Row) -> Slot:
    return Slot(
        id=row["id"],
        starts_at=from_db(row["starts_at"]),
        minutes=row["minutes"],
        is_open=bool(row["is_open"]),
        auto=bool(row["auto"]),
    )


def _booking(row: sqlite3.Row) -> Booking:
    return Booking(
        id=row["id"],
        slot_id=row["slot_id"],
        starts_at=from_db(row["starts_at"]),
        minutes=row["minutes"],
        user=_user(row, "u_"),
        topic=row["topic"],
        comment=row["comment"],
        status=Status(row["status"]),
        cancel_reason=row["cancel_reason"],
        created_at=from_db(row["created_at"]),
        reminded_day=bool(row["reminded_day"]),
        reminded_soon=bool(row["reminded_soon"]),
    )


def _question(row: sqlite3.Row) -> Question:
    return Question(
        id=row["id"],
        user_id=row["user_id"],
        text=row["text"],
        answer=row["answer"],
        status=row["status"],
        created_at=from_db(row["created_at"]),
    )


class Repo:
    """Вся работа с базой. Одно соединение на бота, запросы идут по очереди через lock,
    поэтому транзакции разных обработчиков не перемешиваются."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path | str) -> "Repo":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path, isolation_level=None)
        if str(path) != ":memory:":
            os.chmod(path, 0o600)  # имена учеников и вопросы — только для владельца файла
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.executescript(SCHEMA)
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def _all(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        async with self._lock:
            async with self._conn.execute(sql, tuple(params)) as cur:
                return list(await cur.fetchall())

    async def _one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        async with self._lock:
            async with self._conn.execute(sql, tuple(params)) as cur:
                return await cur.fetchone()

    async def _run(self, sql: str, params: Iterable = ()) -> int:
        async with self._lock:
            cur = await self._conn.execute(sql, tuple(params))
            return cur.rowcount

    # --- пользователи ---------------------------------------------------------

    async def touch_user(self, user_id: int, username: str | None, tg_name: str, now: datetime) -> User:
        row = await self._one(
            """
            INSERT INTO users (id, username, tg_name, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username = excluded.username, tg_name = excluded.tg_name
            RETURNING *
            """,
            (user_id, username, tg_name, to_db(now)),
        )
        assert row is not None
        return _user(row)

    async def get_user(self, user_id: int) -> User | None:
        row = await self._one("SELECT * FROM users WHERE id = ?", (user_id,))
        return _user(row) if row else None

    async def set_profile(self, user_id: int, full_name: str, class_name: str) -> None:
        await self._run("UPDATE users SET full_name = ?, class_name = ? WHERE id = ?", (full_name, class_name, user_id))

    async def set_name(self, user_id: int, full_name: str) -> None:
        await self._run("UPDATE users SET full_name = ? WHERE id = ?", (full_name, user_id))

    async def set_banned(self, user_id: int, banned: bool) -> None:
        await self._run("UPDATE users SET is_banned = ? WHERE id = ?", (int(banned), user_id))

    # --- окошки ---------------------------------------------------------------

    async def ensure_slots(self, starts: Iterable[datetime], minutes: int) -> int:
        rows = [(to_db(dt), minutes) for dt in starts]
        if not rows:
            return 0
        async with self._lock:
            before = self._conn.total_changes
            await self._conn.executemany(
                "INSERT OR IGNORE INTO slots (starts_at, minutes, auto) VALUES (?, ?, 1)", rows
            )
            return self._conn.total_changes - before

    async def get_slot(self, slot_id: int) -> Slot | None:
        row = await self._one("SELECT * FROM slots WHERE id = ?", (slot_id,))
        return _slot(row) if row else None

    async def get_slot_at(self, starts_at: datetime) -> Slot | None:
        row = await self._one("SELECT * FROM slots WHERE starts_at = ?", (to_db(starts_at),))
        return _slot(row) if row else None

    async def put_slot(self, starts_at: datetime, minutes: int, is_open: bool) -> Slot:
        row = await self._one(
            """
            INSERT INTO slots (starts_at, minutes, is_open) VALUES (?, ?, ?)
            ON CONFLICT(starts_at) DO UPDATE SET is_open = excluded.is_open
            RETURNING *
            """,
            (to_db(starts_at), minutes, int(is_open)),
        )
        assert row is not None
        return _slot(row)

    async def free_days(self, not_before: datetime, until: date) -> list[tuple[date, int]]:
        """Дни, в которых есть свободные окошки, и сколько их."""
        rows = await self._all(
            """
            SELECT substr(s.starts_at, 1, 10) AS day, COUNT(*) AS n
            FROM slots s
            WHERE s.is_open = 1 AND s.starts_at >= ? AND s.starts_at < ?
              AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = s.id AND b.status = 'active')
            GROUP BY day ORDER BY day
            """,
            (to_db(not_before), (until + timedelta(days=1)).isoformat()),
        )
        return [(date.fromisoformat(r["day"]), r["n"]) for r in rows]

    async def free_slots(self, day: date, not_before: datetime) -> list[Slot]:
        rows = await self._all(
            """
            SELECT s.* FROM slots s
            WHERE s.is_open = 1 AND s.starts_at >= ? AND substr(s.starts_at, 1, 10) = ?
              AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = s.id AND b.status = 'active')
            ORDER BY s.starts_at
            """,
            (to_db(not_before), day.isoformat()),
        )
        return [_slot(r) for r in rows]

    async def day_slots(self, day: date) -> list[DaySlot]:
        slots = await self._all(
            "SELECT * FROM slots WHERE substr(starts_at, 1, 10) = ? ORDER BY starts_at", (day.isoformat(),)
        )
        bookings = await self._all(
            _BOOKING_SELECT + " WHERE b.status != 'cancelled' AND b.status != 'cancelled_admin'"
            " AND substr(s.starts_at, 1, 10) = ?",
            (day.isoformat(),),
        )
        by_slot = {r["slot_id"]: _booking(r) for r in bookings}
        return [DaySlot(_slot(r), by_slot.get(r["id"])) for r in slots]

    async def days_overview(self, first: date, last: date, not_before: datetime) -> dict[date, tuple[int, int]]:
        """{день: (свободных окошек, записей)} для недельного вида психолога."""
        rows = await self._all(
            """
            SELECT substr(s.starts_at, 1, 10) AS day,
                   SUM(CASE WHEN s.is_open = 1 AND b.id IS NULL AND s.starts_at >= ? THEN 1 ELSE 0 END) AS free,
                   SUM(CASE WHEN b.id IS NOT NULL THEN 1 ELSE 0 END) AS booked
            FROM slots s
            LEFT JOIN bookings b ON b.slot_id = s.id AND b.status IN ('active', 'done', 'missed')
            WHERE s.starts_at >= ? AND s.starts_at < ?
            GROUP BY day
            """,
            (to_db(not_before), first.isoformat(), (last + timedelta(days=1)).isoformat()),
        )
        return {date.fromisoformat(r["day"]): (r["free"], r["booked"]) for r in rows}

    async def close_day(self, day: date, not_before: datetime) -> None:
        """Закрыть всё будущее время дня. Записи остаются, но если их отменят, время уже не откроется."""
        await self._run(
            "UPDATE slots SET is_open = 0 WHERE substr(starts_at, 1, 10) = ? AND starts_at >= ?",
            (day.isoformat(), to_db(not_before)),
        )

    async def close_slot_if_free(self, slot_id: int) -> bool:
        changed = await self._run(
            """
            UPDATE slots SET is_open = 0
            WHERE id = ? AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = slots.id AND b.status = 'active')
            """,
            (slot_id,),
        )
        return changed > 0

    async def prune_auto_slots(self, not_before: datetime, keep: set[datetime], minutes: int) -> None:
        """Убрать окошки, оставшиеся от прошлой сетки (после смены расписания в .env).
        Окошки с действующими записями не трогаем, открытые вручную тоже."""
        keep_keys = {to_db(dt) for dt in keep}
        async with self._lock:
            async with self._conn.execute(
                """
                SELECT s.id, s.starts_at,
                       EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = s.id) AS referenced,
                       EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = s.id AND b.status = 'active') AS booked
                FROM slots s WHERE s.auto = 1 AND s.starts_at >= ?
                """,
                (to_db(not_before),),
            ) as cur:
                rows = list(await cur.fetchall())
            for row in rows:
                if row["booked"]:
                    continue
                if row["starts_at"] in keep_keys:
                    await self._conn.execute("UPDATE slots SET minutes = ? WHERE id = ?", (minutes, row["id"]))
                elif row["referenced"]:
                    await self._conn.execute("UPDATE slots SET is_open = 0 WHERE id = ?", (row["id"],))
                else:
                    await self._conn.execute("DELETE FROM slots WHERE id = ?", (row["id"],))

    # --- записи ---------------------------------------------------------------

    async def create_booking(
        self,
        user_id: int,
        slot_id: int,
        topic: str | None,
        comment: str | None,
        now: datetime,
        not_before: datetime,
        not_after: date,
        max_active: int,
        max_per_day: int,
    ) -> tuple[BookResult, int | None]:
        async with self._lock:
            async with self._conn.execute(
                "SELECT id FROM bookings WHERE slot_id = ? AND user_id = ? AND status = 'active'", (slot_id, user_id)
            ) as cur:
                mine = await cur.fetchone()
            if mine:
                return BookResult.ALREADY, mine["id"]

            async with self._conn.execute(
                """
                SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id = b.slot_id
                WHERE b.user_id = ? AND b.status = 'active' AND s.starts_at >= ?
                """,
                (user_id, to_db(now)),
            ) as cur:
                (active,) = await cur.fetchone()  # type: ignore[misc]
            if active >= max_active:
                return BookResult.LIMIT, None

            async with self._conn.execute(
                "SELECT COUNT(*) FROM bookings WHERE user_id = ? AND created_at >= ?",
                (user_id, to_db(now - timedelta(days=1))),
            ) as cur:
                (recent,) = await cur.fetchone()  # type: ignore[misc]
            if recent >= max_per_day:
                return BookResult.TOO_OFTEN, None

            async with self._conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)) as cur:
                row = await cur.fetchone()
            if (
                row is None
                or not row["is_open"]
                or row["starts_at"] < to_db(not_before)
                or row["starts_at"] >= (not_after + timedelta(days=1)).isoformat()
            ):
                return BookResult.UNAVAILABLE, None

            try:
                cur = await self._conn.execute(
                    "INSERT INTO bookings (slot_id, user_id, topic, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                    (slot_id, user_id, topic, comment, to_db(now)),
                )
            except sqlite3.IntegrityError:
                return BookResult.TAKEN, None
            return BookResult.OK, cur.lastrowid

    async def get_booking(self, booking_id: int) -> Booking | None:
        row = await self._one(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,))
        return _booking(row) if row else None

    async def upcoming_for_user(self, user_id: int, now: datetime) -> list[Booking]:
        rows = await self._all(
            _BOOKING_SELECT + " WHERE b.user_id = ? AND b.status = 'active' AND s.starts_at >= ? ORDER BY s.starts_at",
            (user_id, to_db(now)),
        )
        return [_booking(r) for r in rows]

    async def cancel_booking(self, booking_id: int, by_admin: bool, reason: str | None, now: datetime) -> bool:
        """Если отменяет психолог, время закрывается: раз он отменил, значит, сам в это время занят."""
        status = Status.CANCELLED_ADMIN if by_admin else Status.CANCELLED
        async with self._lock:
            cur = await self._conn.execute(
                """
                UPDATE bookings SET status = ?, cancel_reason = ?, cancelled_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (status.value, reason, to_db(now), booking_id),
            )
            if cur.rowcount == 0:
                return False
            if by_admin:
                await self._conn.execute(
                    "UPDATE slots SET is_open = 0 WHERE id = (SELECT slot_id FROM bookings WHERE id = ?)", (booking_id,)
                )
            return True

    async def active_booking(self, user_id: int, slot_id: int) -> Booking | None:
        row = await self._one(
            _BOOKING_SELECT + " WHERE b.user_id = ? AND b.slot_id = ? AND b.status = 'active'", (user_id, slot_id)
        )
        return _booking(row) if row else None

    async def set_status(self, booking_id: int, status: Status) -> bool:
        changed = await self._run(
            "UPDATE bookings SET status = ? WHERE id = ? AND status IN ('active', 'done', 'missed')",
            (status.value, booking_id),
        )
        return changed > 0

    async def bookings_between(self, start: datetime, end: datetime, statuses: Iterable[Status]) -> list[Booking]:
        statuses = [s.value for s in statuses]
        marks = ",".join("?" * len(statuses))
        rows = await self._all(
            _BOOKING_SELECT + f" WHERE s.starts_at >= ? AND s.starts_at < ? AND b.status IN ({marks}) ORDER BY s.starts_at",
            (to_db(start), to_db(end), *statuses),
        )
        return [_booking(r) for r in rows]

    async def reminder_candidates(self, now: datetime, horizon: timedelta) -> list[Booking]:
        rows = await self._all(
            _BOOKING_SELECT
            + " WHERE b.status = 'active' AND s.starts_at > ? AND s.starts_at <= ?"
            " AND (b.reminded_day = 0 OR b.reminded_soon = 0) ORDER BY s.starts_at",
            (to_db(now), to_db(now + horizon)),
        )
        return [_booking(r) for r in rows]

    async def mark_reminded(self, booking_id: int, day: bool = False, soon: bool = False) -> None:
        await self._run(
            "UPDATE bookings SET reminded_day = reminded_day OR ?, reminded_soon = reminded_soon OR ? WHERE id = ?",
            (int(day), int(soon), booking_id),
        )

    async def month_bookings(self, year: int, month: int) -> list[Booking]:
        prefix = f"{year:04d}-{month:02d}"
        rows = await self._all(
            _BOOKING_SELECT + " WHERE substr(s.starts_at, 1, 7) = ? ORDER BY s.starts_at, b.id", (prefix,)
        )
        return [_booking(r) for r in rows]

    # --- анонимные вопросы ----------------------------------------------------

    async def add_question(self, user_id: int, text: str, now: datetime) -> int:
        async with self._lock:
            cur = await self._conn.execute(
                "INSERT INTO questions (user_id, text, created_at) VALUES (?, ?, ?)", (user_id, text, to_db(now))
            )
            return cur.lastrowid  # type: ignore[return-value]

    async def questions_since(self, user_id: int, since: datetime) -> int:
        row = await self._one(
            "SELECT COUNT(*) AS n FROM questions WHERE user_id = ? AND created_at >= ?", (user_id, to_db(since))
        )
        return row["n"] if row else 0

    async def get_question(self, question_id: int) -> Question | None:
        row = await self._one("SELECT * FROM questions WHERE id = ?", (question_id,))
        return _question(row) if row else None

    async def new_questions(self) -> list[Question]:
        rows = await self._all("SELECT * FROM questions WHERE status = 'new' ORDER BY id")
        return [_question(r) for r in rows]

    async def answer_question(self, question_id: int, answer: str, now: datetime) -> bool:
        changed = await self._run(
            "UPDATE questions SET answer = ?, status = 'answered', answered_at = ? WHERE id = ? AND status = 'new'",
            (answer, to_db(now), question_id),
        )
        return changed > 0

    async def reopen_question(self, question_id: int) -> None:
        await self._run(
            "UPDATE questions SET answer = NULL, status = 'new', answered_at = NULL WHERE id = ? AND status = 'answered'",
            (question_id,),
        )

    async def forget_authors(self, before: datetime) -> None:
        """Стереть связь «вопрос → автор» у вопросов, с которыми уже разобрались."""
        await self._run(
            "UPDATE questions SET user_id = NULL WHERE status != 'new' AND user_id IS NOT NULL AND created_at < ?",
            (to_db(before),),
        )

    async def hide_question(self, question_id: int) -> None:
        await self._run("UPDATE questions SET status = 'hidden' WHERE id = ? AND status = 'new'", (question_id,))

    async def hide_questions_of(self, user_id: int) -> None:
        await self._run("UPDATE questions SET status = 'hidden' WHERE user_id = ? AND status = 'new'", (user_id,))

    # --- служебное ------------------------------------------------------------

    async def get_kv(self, key: str) -> str | None:
        row = await self._one("SELECT value FROM kv WHERE key = ?", (key,))
        return row["value"] if row else None

    async def set_kv(self, key: str, value: str) -> None:
        await self._run(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def slot_starts(days: Iterable[date], times: Iterable[time]) -> list[datetime]:
    times = list(times)
    return [datetime.combine(d, t) for d in days for t in times]
