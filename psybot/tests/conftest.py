import sys
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.config import Settings  # noqa: E402
from bot.db import Repo  # noqa: E402
from bot.scheduler import fill_schedule  # noqa: E402
from harness import FakeClock, Harness  # noqa: E402

ADMIN = 999
STUDENT = 501
OTHER = 502

MONDAY_MORNING = datetime(2026, 10, 5, 8, 30)


def make_config(**overrides) -> Settings:
    values = dict(
        bot_token="123456:TEST-TOKEN",
        admin_ids=[ADMIN],
        psychologist_name="Мария Ивановна Соколова",
        psychologist_room="кабинет 214",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def config() -> Settings:
    return make_config()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(MONDAY_MORNING)


@pytest_asyncio.fixture
async def repo():
    repo = await Repo.open(":memory:")
    yield repo
    await repo.close()


@pytest_asyncio.fixture
async def h(config, repo, clock) -> Harness:
    await fill_schedule(repo, clock.now().date(), config)
    harness = Harness(config, repo, clock)
    harness.user(ADMIN, "Мария")
    harness.user(STUDENT, "Аня", "anya_s")
    harness.user(OTHER, "Петя")
    return harness
