"""Команды, описание и аватарка бота в Telegram."""

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, FSInputFile, InputProfilePhotoStatic

from . import texts
from .config import Settings

log = logging.getLogger(__name__)

AVATAR = Path(__file__).resolve().parent.parent / "assets" / "avatar.jpg"

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="book", description="Записаться к психологу"),
    BotCommand(command="my", description="Мои записи"),
    BotCommand(command="ask", description="Задать вопрос анонимно"),
    BotCommand(command="help", description="Если плохо прямо сейчас"),
]
ADMIN_COMMANDS = [*COMMANDS, BotCommand(command="admin", description="Кабинет психолога")]


def description(config: Settings) -> str:
    return texts.BOT_DESCRIPTION.format(school=config.school_name)


def short_description(config: Settings) -> str:
    return texts.BOT_SHORT_DESCRIPTION.format(school=config.school_name)


async def setup_profile(bot: Bot, config: Settings) -> None:
    try:
        await bot.set_my_commands(COMMANDS, scope=BotCommandScopeDefault())
        if (await bot.get_my_description()).description != description(config):
            await bot.set_my_description(description(config))
        if (await bot.get_my_short_description()).short_description != short_description(config):
            await bot.set_my_short_description(short_description(config))
    except TelegramAPIError as e:
        log.warning("Не удалось обновить профиль бота: %s", e)
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as e:
            log.warning("Не удалось поставить команды психологу %s (он уже нажал «Старт»?): %s", admin_id, e)


async def set_avatar(bot: Bot) -> None:
    await bot.set_my_profile_photo(InputProfilePhotoStatic(photo=FSInputFile(AVATAR)))
