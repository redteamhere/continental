"""
Shared PIN-pad handlers — digit input and backspace only.
Each flow's `pin:submit` is handled locally (start.py, deals.py)
with a state filter so there is no ambiguity.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.pin_kb import MAX_PIN, pin_dots, pin_pad_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.deal_creation import DealCreationStates
from app.bot.states.registration import RegistrationStates

router = Router()

# ── Per-state display config (title, subtitle, cancel callback) ──────────────
_CFG: dict[str | None, tuple[str, str, str]] = {
    RegistrationStates.waiting_for_pin.state: (
        "🔐 <b>Create PIN</b>",
        "Choose a 4–8 digit security PIN.\nTap ✅ when done.",
        "pin:cancel_reg",
    ),
    RegistrationStates.confirm_pin.state: (
        "🔐 <b>Confirm PIN</b>",
        "Re-enter your PIN to confirm.",
        "pin:cancel_reg",
    ),
    DealCreationStates.confirm_pin.state: (
        "🔐 <b>Confirm Deal</b>",
        "Enter your PIN to create the deal.",
        "deal:cancel_creation",
    ),
    "ReleasePinState:verify": (
        "🔐 <b>Release Funds</b>",
        "Enter your PIN to release funds to the seller.",
        "pin:cancel",
    ),
}

_DEFAULT_CFG = ("🔐 <b>Enter PIN</b>", "", "pin:cancel")


def build_pin_message(state_str: str | None, digits: int) -> tuple[str, object]:
    title, subtitle, cancel = _CFG.get(state_str, _DEFAULT_CFG)
    dots = pin_dots(digits)
    body = f"\n{subtitle}" if subtitle else ""
    text = f"{title}{body}\n\n<code>{dots}</code>"
    return text, pin_pad_kb(digits, cancel_data=cancel)


# ── Handlers ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pin:d:"))
async def pin_digit(callback: CallbackQuery, state: FSMContext) -> None:
    state_str = await state.get_state()
    if state_str not in _CFG:
        await callback.answer()
        return

    digit = callback.data.split(":")[2]
    data = await state.get_data()
    buf = data.get("pin_buffer", "")
    if len(buf) >= MAX_PIN:
        await callback.answer("Maximum PIN length reached.", show_alert=True)
        return

    buf += digit
    await state.update_data(pin_buffer=buf)
    text, kb = build_pin_message(state_str, len(buf))
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "pin:back")
async def pin_backspace(callback: CallbackQuery, state: FSMContext) -> None:
    state_str = await state.get_state()
    if state_str not in _CFG:
        await callback.answer()
        return

    data = await state.get_data()
    buf = data.get("pin_buffer", "")[:-1]
    await state.update_data(pin_buffer=buf)
    text, kb = build_pin_message(state_str, len(buf))
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "pin:cancel")
async def pin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("Cancelled.", reply_markup=main_menu_kb())
    except Exception:
        await callback.message.answer("Cancelled.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "pin:cancel_reg")
async def pin_cancel_reg(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("Registration cancelled. Use /start to try again.")
    except Exception:
        pass
    await callback.answer()
