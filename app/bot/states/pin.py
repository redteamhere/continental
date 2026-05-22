from aiogram.fsm.state import State, StatesGroup


class PinStates(StatesGroup):
    verify = State()       # User entering PIN for a protected action
    set_new = State()      # Setting a new PIN (first time)
    confirm_new = State()  # Confirming new PIN
    change_old = State()   # Verifying old PIN before changing
    change_new = State()   # Entering new PIN
    change_confirm = State()
