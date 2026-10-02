"""Анонимные вопросы: психолог видит только текст, ответ бот пересылает автору."""

import re

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens, screens
from ...callbacks import Admin, AdmQuestion
from ...db import Repo
from ...filters import TEXT
from ...notify import Delivery, send
from ...states import AdminInput
from ...timeutil import Clock
from ...ui import show

router = Router(name="admin_questions")

# вместе с заголовком и цитатой вопроса сообщение должно влезть в 4096 символов Telegram
ANSWER_LIMIT = 3000
# «Новый анонимный вопрос #12», «Вопрос #12», «Ответ на вопрос #12»
QUESTION_REF = re.compile(r"вопрос #(\d+)", re.IGNORECASE)


@router.callback_query(Admin.filter(F.to == "questions"))
async def questions(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.clear()
    await show(callback, admin_screens.questions(await repo.new_questions()))


@router.callback_query(AdmQuestion.filter())
async def question_action(callback: CallbackQuery, callback_data: AdmQuestion, callback_answer: CallbackAnswer,
                          state: FSMContext, repo: Repo, clock: Clock) -> None:
    await state.clear()
    question = await repo.get_question(callback_data.id)
    if question is None:
        callback_answer.text = "Вопрос не найден"
        return
    action = callback_data.action
    if action != "view" and question.status != "new":
        callback_answer.text = "С этим вопросом уже разобрались"
        action = "view"

    if action == "reply":
        await state.set_state(AdminInput.answer)
        await state.set_data({"question_id": question.id})
        await show(callback, admin_screens.answer_prompt(question, ANSWER_LIMIT))
    elif action == "hide":
        await repo.hide_question(question.id)
        callback_answer.text = "Вопрос скрыт, автор ответа не получит"
        await show(callback, admin_screens.questions(await repo.new_questions()))
    elif action == "ban":
        await show(callback, admin_screens.ban_confirm(question))
    elif action == "ban_yes" and question.user_id is not None:
        await repo.set_banned(question.user_id, True)
        await repo.hide_questions_of(question.user_id)
        callback_answer.text = "Готово, автор больше не сможет писать"
        await show(callback, admin_screens.questions(await repo.new_questions()))
    else:
        await show(callback, admin_screens.question(question, clock.now().date()))


async def deliver(message: Message, question_id: int, repo: Repo, clock: Clock, bot: Bot) -> bool:
    """Отправить ответ автору. False — ответ слишком длинный, его надо прислать заново."""
    answer = (message.text or "").strip()
    if len(answer) > ANSWER_LIMIT:
        await message.answer(
            f"Получилось {len(answer)} символов, а в ответ помещается до {ANSWER_LIMIT}. "
            "Сократите, пожалуйста, и пришлите ещё раз."
        )
        return False
    question = await repo.get_question(question_id)
    # сначала помечаем вопрос отвеченным: если два психолога ответят одновременно, уйдёт один ответ
    if question is None or question.user_id is None or not await repo.answer_question(question.id, answer, clock.now()):
        await message.answer("На этот вопрос уже ответили.")
    else:
        delivery = await send(bot, question.user_id, screens.answer_to_student(question.text, answer))
        if delivery is Delivery.OK:
            await message.answer("Ответ отправлен.")
        elif delivery is Delivery.GONE:
            await message.answer("Ответ не дошёл: автор остановил бота.")
        else:
            await repo.reopen_question(question.id)
            await message.answer("Ответ не отправился: Telegram не принял сообщение. Вопрос остался в списке, "
                                 "попробуйте ещё раз чуть позже.")
    await show(message, admin_screens.questions(await repo.new_questions()))
    return True


@router.message(AdminInput.answer, TEXT)
async def got_answer(message: Message, state: FSMContext, repo: Repo, clock: Clock, bot: Bot) -> None:
    data = await state.get_data()
    if await deliver(message, data["question_id"], repo, clock, bot):
        await state.clear()


@router.message(StateFilter(None), TEXT, F.reply_to_message)
async def reply_to_question(message: Message, repo: Repo, clock: Clock, bot: Bot) -> None:
    """Ответ свайпом на уведомление или карточку вопроса — тоже ответ на вопрос."""
    replied = message.reply_to_message
    is_ours = replied is not None and replied.from_user is not None and replied.from_user.is_bot
    match = QUESTION_REF.search(replied.text or "") if is_ours and replied else None
    if match is None:
        raise SkipHandler
    await deliver(message, int(match.group(1)), repo, clock, bot)
