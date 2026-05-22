from aiogram.fsm.state import State, StatesGroup


class DisputeStates(StatesGroup):
    enter_reason = State()
    upload_evidence = State()
    confirm_pin = State()


class AdminResolveStates(StatesGroup):
    select_resolution = State()
    enter_split_percent = State()
    enter_notes = State()
    confirm = State()
