"""
Shared PIN handlers:
  - digit / backspace for inline PIN pad
  - web_app_data for the Telegram Mini App PIN screen
Each flow's pin:submit is handled locally with a state filter.
"""
from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

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


# ── Telegram Mini App — receives PIN from webapp/pin.html ─────────────────────

@router.message(F.web_app_data)
async def web_app_pin_received(message: Message, state: FSMContext, db_user) -> None:
    """
    Called when the HTML PIN screen sends data via Telegram.WebApp.sendData().
    Payload: {"pin": "1234", "mode": "set"|"verify"}
    Dispatches to the correct flow based on current FSM state.
    """
    try:
        payload = json.loads(message.web_app_data.data)
        pin = payload.get("pin", "")
        mode = payload.get("mode", "verify")
    except Exception:
        await message.answer("❌ Invalid PIN data received.")
        return

    if not pin or not pin.isdigit() or not (4 <= len(pin) <= 8):
        await message.answer("❌ Invalid PIN. Please try again.")
        return

    state_str = await state.get_state()

    if mode == "set" and state_str == RegistrationStates.waiting_for_pin.state:
        await _webapp_register(message, state, pin)

    elif mode == "verify" and state_str == DealCreationStates.confirm_pin.state:
        await _webapp_deal_pin(message, state, pin)

    elif mode == "verify" and state_str == "ReleasePinState:verify":
        await _webapp_release_pin(message, state, pin)

    else:
        await message.answer("❌ Unexpected PIN entry. Please start over.")
        await state.clear()


async def _webapp_register(message: Message, state: FSMContext, pin: str) -> None:
    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService
    from app.bot.keyboards.main_menu import main_menu_kb as _menu_kb

    data = await state.get_data()

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.create(
            telegram_id=message.from_user.id,
            first_name=data.get("tg_first_name", "User"),
            last_name=data.get("tg_last_name"),
            username=data.get("tg_username"),
            language_code=data.get("tg_lang", "en"),
            referral_code_used=data.get("referral_code"),
        )
        await svc.set_pin(user, pin)
        await audit.pin_set(user.id)
        await session.commit()

    await state.clear()
    await message.answer(
        f"🎉 <b>Account created!</b>\n\n"
        f"Your referral code: <code>{user.referral_code}</code>\n\n"
        f"You're all set. Explore the menu below.",
        reply_markup=_menu_kb(),
        parse_mode="HTML",
    )


async def _webapp_deal_pin(message: Message, state: FSMContext, pin: str) -> None:
    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService
    from app.security.pin_manager import PinManager

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)

        if PinManager.is_locked(user.pin_locked_until):
            secs = PinManager.seconds_until_unlock(user.pin_locked_until)
            await message.answer(f"🔒 PIN locked. Try again in {secs // 60}m {secs % 60}s.")
            await state.clear()
            return

        ok = await svc.verify_pin(user, pin)
        if not ok:
            await AuditService(session).pin_failed(user.id)
            await session.commit()
            await message.answer("❌ Wrong PIN. Deal creation cancelled.")
            await state.clear()
            return
        await session.commit()

    # Delegate to deal finalization
    from app.bot.handlers.deals import _finalize_deal_creation
    await _finalize_deal_creation(message, state)


async def _webapp_release_pin(message: Message, state: FSMContext, pin: str) -> None:
    from datetime import datetime, timezone
    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService
    from app.services.deal_service import DealService
    from app.services.escrow_service import EscrowService
    from app.services.notification_service import NotificationService
    from app.bot.keyboards.deal_kb import review_stars_kb
    from app.security.pin_manager import PinManager

    data = await state.get_data()
    deal_id = data.get("pending_release_deal_id")

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)

        if PinManager.is_locked(user.pin_locked_until):
            secs = PinManager.seconds_until_unlock(user.pin_locked_until)
            await message.answer(f"🔒 PIN locked. Try again in {secs // 60}m {secs % 60}s.")
            await state.clear()
            return

        ok = await svc.verify_pin(user, pin)
        if not ok:
            await AuditService(session).pin_failed(user.id)
            await session.commit()
            await message.answer("❌ Wrong PIN. Release cancelled.")
            await state.clear()
            return

        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        notif_svc = NotificationService(session, message.bot)
        audit = AuditService(session)

        deal = await deal_svc.get_by_id(deal_id)
        if not deal or deal.buyer_id != user.id:
            await message.answer("Deal not found.")
            await state.clear()
            return

        await deal_svc.complete(deal, user)
        await escrow_svc.release_funds_to_seller(deal)
        seller = await UserService(session).get_by_id(deal.seller_id)
        await notif_svc.deal_completed(deal, user, seller)
        await audit.deal_completed(user.id, deal.id)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Funds Released!</b>\n\nDeal <code>{deal.deal_number}</code> is complete.\n"
        f"Please leave a review for the seller.",
        reply_markup=review_stars_kb(deal.id),
        parse_mode="HTML",
    )
