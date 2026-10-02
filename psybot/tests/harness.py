"""Бот без Telegram: подменяем сетевую сессию и кормим диспетчер апдейтами вручную.
Так можно пройти любой сценарий целиком и проверить, что увидит человек."""

import itertools
from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendDocument,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)

from bot.app import create_dispatcher
from bot.config import Settings
from bot.db import Repo
from bot.timeutil import Clock

BOT_USER = User(id=1, is_bot=True, first_name="Психолог ЛИТ", username="psy1533_bot")


class FakeClock(Clock):
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


@dataclass
class Sent:
    """Сообщение бота в чате так, как его сейчас видит человек."""

    chat_id: int
    message_id: int
    text: str
    markup: InlineKeyboardMarkup | None
    document: str | None = None
    document_bytes: bytes | None = None
    history: list[str] = field(default_factory=list)

    @property
    def buttons(self) -> list[InlineKeyboardButton]:
        if not self.markup:
            return []
        return [b for row in self.markup.inline_keyboard for b in row]


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.ids = itertools.count(100)
        self.messages: dict[tuple[int, int], Sent] = {}
        self.log: list[tuple[str, object]] = []
        self.alerts: list[tuple[str | None, bool]] = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def _message(self, sent: Sent) -> Message:
        return Message(
            message_id=sent.message_id,
            date=datetime.now(),
            chat=Chat(id=sent.chat_id, type="private"),
            from_user=BOT_USER,
            text=sent.text,
            reply_markup=sent.markup,
        )

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):
        self.log.append((type(method).__name__, method))
        if isinstance(method, SendMessage):
            self._validate(method.text, method.reply_markup)
            sent = Sent(int(method.chat_id), next(self.ids), method.text, method.reply_markup)
            self.messages[(sent.chat_id, sent.message_id)] = sent
            return self._message(sent)
        if isinstance(method, EditMessageText):
            self._validate(method.text, method.reply_markup)
            sent = self.messages[(int(method.chat_id), int(method.message_id))]
            if sent.text == method.text and sent.markup == method.reply_markup:
                raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")
            sent.history.append(sent.text)
            sent.text, sent.markup = method.text, method.reply_markup
            return self._message(sent)
        if isinstance(method, EditMessageReplyMarkup):
            sent = self.messages[(int(method.chat_id), int(method.message_id))]
            sent.markup = method.reply_markup
            return self._message(sent)
        if isinstance(method, AnswerCallbackQuery):
            self.alerts.append((method.text, bool(method.show_alert)))
            return True
        if isinstance(method, SendDocument):
            sent = Sent(int(method.chat_id), next(self.ids), method.caption or "", None,
                        document=method.document.filename, document_bytes=method.document.data)
            self.messages[(sent.chat_id, sent.message_id)] = sent
            msg = self._message(sent)
            return msg.model_copy(update={"document": Document(file_id="f", file_unique_id="u")})
        return True

    @staticmethod
    def _validate(text: str, markup: InlineKeyboardMarkup | None) -> None:
        """Те же ограничения, что проверяет Telegram, чтобы тесты ловили их заранее."""
        assert text and len(text) <= 4096, f"текст сообщения пустой или длиннее 4096: {len(text)}"
        if markup:
            buttons = [b for row in markup.inline_keyboard for b in row]
            assert len(buttons) <= 100, "больше 100 кнопок"
            for b in buttons:
                assert b.callback_data is None or len(b.callback_data.encode()) <= 64, b.callback_data
                assert b.text.strip(), "пустая кнопка"


_dispatcher: Dispatcher | None = None


def shared_dispatcher(config: Settings, repo: Repo, clock: Clock) -> Dispatcher:
    """Роутеры aiogram подключаются к диспетчеру один раз, поэтому диспетчер общий на все тесты,
    а база, часы, настройки и состояния у каждого теста свои."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = create_dispatcher(config, repo, clock)
    _dispatcher.workflow_data.update(config=config, repo=repo, clock=clock)
    _dispatcher.fsm.storage = MemoryStorage()
    return _dispatcher


class Harness:
    def __init__(self, config: Settings, repo: Repo, clock: FakeClock) -> None:
        self.config, self.repo, self.clock = config, repo, clock
        self.session = FakeSession()
        self.bot = Bot(
            "123456:TEST-TOKEN",
            session=self.session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
        )
        self.dp = shared_dispatcher(config, repo, clock)
        self.update_ids = itertools.count(1)
        self.users: dict[int, User] = {}

    def user(self, user_id: int, first_name: str = "Аня", username: str | None = None) -> User:
        self.users[user_id] = User(id=user_id, is_bot=False, first_name=first_name, username=username)
        return self.users[user_id]

    async def send(self, user_id: int, text: str) -> None:
        message = Message(
            message_id=next(self.session.ids),
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=self.users[user_id],
            text=text,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self.update_ids), message=message))

    def chat(self, user_id: int) -> list[Sent]:
        return [m for (chat_id, _), m in sorted(self.session.messages.items()) if chat_id == user_id]

    def last(self, user_id: int) -> Sent:
        return self.chat(user_id)[-1]

    def find_button(self, user_id: int, label: str) -> tuple[Sent, InlineKeyboardButton]:
        for sent in reversed(self.chat(user_id)):
            for b in sent.buttons:
                if label in b.text:
                    return sent, b
        raise AssertionError(f"нет кнопки «{label}» у {user_id}. Последний экран:\n{self.last(user_id).text}")

    async def press(self, user_id: int, label: str) -> None:
        sent, button = self.find_button(user_id, label)
        await self.press_data(user_id, sent, button.callback_data or "")

    async def press_data(self, user_id: int, sent: Sent, data: str) -> None:
        callback = CallbackQuery(
            id=str(next(self.update_ids)),
            from_user=self.users[user_id],
            chat_instance="test",
            message=self.session._message(sent),
            data=data,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self.update_ids), callback_query=callback))

    @property
    def last_alert(self) -> str | None:
        return self.session.alerts[-1][0] if self.session.alerts else None

