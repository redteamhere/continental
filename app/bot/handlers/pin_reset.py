"""PIN reset — self-service 'Forgot PIN?' flow and admin /reset_pin command."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.pin_input import build_pin_message
from app.bot.keyboards.pin_kb import pin_webapp_kb
from app.bot.states.pin_reset import PinResetStates

router = Router()


# ── Step 1 — User taps "Forgot PIN?" ─────────────────────────────────────────

@router.callback_query(F.data == "pin:forgot")
async def pin_forgot(callback: CallbackQuery, state: FSMContext) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes, reset my PIN", callback_data="pin:forgot_confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="pin:forgot_cancel"),
    ]])
    try:
        await callback.message.edit_text(
            "🔑 <b>Reset your PIN?</b>\n\n"
            "You will need to create a new PIN before you can continue.\n"
            "All your active deals and balance are <b>not affected</b>.\n\n"
            "Are you sure you want to reset your PIN?",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            "🔑 <b>Reset your PIN?</b>\n\nAre you sure?",
            reply_markup=kb,
            parse_mode="HTML",
        )
    await callback.answer()


# ── Step 2 — User cancels ─────────────────────────────────────────────────────

@router.callback_query(F.data == "pin:forgot_cancel")
async def pin_forgot_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    state_str = await state.get_state()
    text, kb = build_pin_message(state_str, 0)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


# ── Step 3 — User confirms reset ─────────────────────────────────────────────

@router.callback_query(F.data == "pin:forgot_confirm")
async def pin_forgot_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService
    from app.config import settings as _settings

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        await svc.reset_pin(user)
        await AuditService(session).pin_reset(user.id)
        await session.commit()

    await state.update_data(pin_buffer="")
    await state.set_state(PinResetStates.waiting_for_new_pin)

    if _settings.WEB_APP_URL:
        try:
            await callback.message.edit_text(
                "✅ <b>PIN cleared.</b>\n\nNow set your new PIN.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.message.answer(
            "🔑 <b>Set your new PIN</b>\n\nTap the button below.",
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await callback.answer("PIN reset. Set a new PIN.")


# ── Inline PIN pad submit handlers for reset flow ────────────────────────────

@router.callback_query(F.data == "pin:submit", PinResetStates.waiting_for_new_pin)
async def reset_pin_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await callback.answer("Enter a 4–8 digit PIN.", show_alert=True)
        return

    await state.update_data(pin=pin, pin_buffer="")
    await state.set_state(PinResetStates.confirm_new_pin)

    text, kb = build_pin_message(PinResetStates.confirm_new_pin.state, 0)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pin:submit", PinResetStates.confirm_new_pin)
async def reset_pin_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService
    from app.bot.keyboards.main_menu import main_menu_kb

    data = await state.get_data()
    confirm = data.get("pin_buffer", "")

    if confirm != data.get("pin"):
        await state.update_data(pin_buffer="")
        await state.set_state(PinResetStates.waiting_for_new_pin)
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        await callback.message.edit_text(
            "❌ PINs don't match. Enter your new PIN again:\n\n"
            + text.split("\n\n", 1)[-1],
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)
        await svc.set_pin(user, data["pin"])
        await AuditService(session).pin_reset(user.id)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>New PIN set!</b>\n\n"
        "Your PIN has been changed. Go back to your deal and try again.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Admin force-reset ─────────────────────────────────────────────────────────

def _is_admin(db_user, tg_id: int) -> bool:
    from app.config import settings
    return bool(
        (db_user and db_user.is_moderator)
        or tg_id in settings.ADMIN_IDS
    )


@router.message(Command("reset_pin"))
async def admin_reset_pin(message: Message, db_user) -> None:
    """Admin only: /reset_pin <telegram_id_or_@username>"""
    if not _is_admin(db_user, message.from_user.id):
        await message.answer("⛔ You don't have permission to use this command.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage:\n"
            "<code>/reset_pin 123456789</code>  (Telegram ID)\n"
            "<code>/reset_pin @username</code>",
            parse_mode="HTML",
        )
        return

    target_str = parts[1].strip()

    from app.database import AsyncSessionFactory
    from app.services.user_service import UserService
    from app.services.audit_service import AuditService

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        if target_str.startswith("@"):
            target = await svc.get_by_username(target_str.lstrip("@"))
        elif target_str.isdigit():
            target = await svc.get_by_telegram_id(int(target_str))
        else:
            target = None

        if not target:
            await message.answer(f"❌ User <code>{target_str}</code> not found.", parse_mode="HTML")
            return

        await svc.reset_pin(target)
        await AuditService(session).pin_reset(target.id, by_admin_id=db_user.id)
        await session.commit()
        target_name = target.display_name
        target_tg_id = target.telegram_id

    # Notify the affected user
    try:
        await message.bot.send_message(
            target_tg_id,
            "🔑 <b>Your PIN has been reset by an administrator.</b>\n\n"
            "Please use /start to set a new PIN before your next transaction.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ PIN reset for <b>{target_name}</b> (<code>{target_tg_id}</code>).\n"
        f"They have been notified.",
        parse_mode="HTML",
    )
