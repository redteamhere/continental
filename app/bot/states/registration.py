from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    select_language = State()   # NEW: shown before PIN creation
    waiting_for_pin = State()
    confirm_pin = State()
