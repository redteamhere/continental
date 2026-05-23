from aiogram.fsm.state import State, StatesGroup


class PinResetStates(StatesGroup):
    waiting_for_new_pin = State()
    confirm_new_pin = State()
