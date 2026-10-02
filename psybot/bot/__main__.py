"""Запуск: python -m bot. Поставить аватарку: python -m bot set-avatar"""

import asyncio
import contextlib
import logging
import os
import sys

from . import scheduler
from .app import create_bot, create_dispatcher
from .config import Settings
from .db import Repo
from .setup import set_avatar, setup_profile
from .timeutil import Clock


async def main() -> None:
    os.umask(0o077)  # база с именами и вопросами доступна только тому, кто запустил бота
    config = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bot = create_bot(config)

    if sys.argv[1:] == ["set-avatar"]:
        async with bot:
            await set_avatar(bot)
        print("Аватарка обновлена")
        return

    repo = await Repo.open(config.db_path)
    clock = Clock(config.tz)
    dp = create_dispatcher(config, repo, clock)
    if not config.admin_ids:
        logging.warning("ADMIN_IDS не задан: уведомления о записях и кабинет психолога работать не будут")

    await setup_profile(bot, config)
    background = asyncio.create_task(scheduler.run(bot, repo, clock, config))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        background.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await background
        await repo.close()
        await bot.session.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
