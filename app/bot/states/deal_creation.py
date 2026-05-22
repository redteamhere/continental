from aiogram.fsm.state import State, StatesGroup


class DealCreationStates(StatesGroup):
    enter_seller = State()
    enter_description = State()
    enter_amount = State()
    select_currency = State()
    enter_deadline = State()
    enter_terms = State()
    confirm_pin = State()
    review_and_confirm = State()
