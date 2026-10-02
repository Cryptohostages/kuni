import html
from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"


@dataclass(slots=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup | None = None


def btn(text: str, data: CallbackData | str, style: str | None = None) -> InlineKeyboardButton:
    callback_data = data if isinstance(data, str) else data.pack()
    return InlineKeyboardButton(text=text, callback_data=callback_data, style=style)


def kb(*rows: list[InlineKeyboardButton] | InlineKeyboardButton) -> InlineKeyboardMarkup:
    keyboard = [row if isinstance(row, list) else [row] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=[row for row in keyboard if row])


def chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


async def show(event: Message | CallbackQuery, screen: Screen) -> None:
    """Показать экран: по нажатию кнопки — переписать то же сообщение, иначе — отправить новое."""
    if isinstance(event, Message):
        await event.answer(screen.text, reply_markup=screen.markup)
        return
    if isinstance(event.message, Message):
        try:
            await event.message.edit_text(screen.text, reply_markup=screen.markup)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                return
    assert event.bot is not None
    await event.bot.send_message(event.from_user.id, screen.text, reply_markup=screen.markup)
