"""Анонимные вопросы: психолог видит только текст, ответ бот пересылает автору."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from ... import admin_screens, screens
from ...callbacks import Admin, AdmQuestion
from ...db import Repo
from ...filters import TEXT
from ...notify import send
from ...states import AdminInput
from ...timeutil import Clock
from ...ui import show

router = Router(name="admin_questions")


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
        await show(callback, admin_screens.answer_prompt(question))
    elif action == "hide":
        await repo.hide_question(question.id)
        callback_answer.text = "Вопрос скрыт"
        await show(callback, admin_screens.questions(await repo.new_questions()))
    elif action == "ban":
        await show(callback, admin_screens.ban_confirm(question))
    elif action == "ban_yes":
        await repo.set_banned(question.user_id, True)
        await repo.hide_questions_of(question.user_id)
        callback_answer.text = "Готово, автор больше не сможет писать"
        await show(callback, admin_screens.questions(await repo.new_questions()))
    else:
        await show(callback, admin_screens.question(question, clock.now().date()))


@router.message(AdminInput.answer, TEXT)
async def got_answer(message: Message, state: FSMContext, repo: Repo, clock: Clock, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    question = await repo.get_question(data["question_id"])
    answer = (message.text or "").strip()
    if question is None or not await repo.answer_question(question.id, answer, clock.now()):
        await message.answer("На этот вопрос уже ответили.")
    elif await send(bot, question.user_id, screens.answer_to_student(question.text, answer)):
        await message.answer("Ответ отправлен.")
    else:
        await message.answer("Ответ сохранён, но не дошёл: похоже, автор остановил бота.")
    await show(message, admin_screens.questions(await repo.new_questions()))
