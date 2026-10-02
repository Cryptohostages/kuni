from aiogram.fsm.state import State, StatesGroup


class Profile(StatesGroup):
    name = State()
    class_name = State()


class Booking(StatesGroup):
    comment = State()


class Ask(StatesGroup):
    text = State()


class AdminInput(StatesGroup):
    cancel_reason = State()
    answer = State()
    custom_time = State()
