from aiogram.fsm.state import State, StatesGroup


class DiscountState(StatesGroup):
    code = State()


class SupportState(StatesGroup):
    message = State()
