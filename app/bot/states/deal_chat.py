from aiogram.fsm.state import State, StatesGroup


class DealChatState(StatesGroup):
    active = State()
