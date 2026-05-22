"""Registration and main menu."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.main_menu import main_menu_kb, back_kb
from app.bot.states.registration import RegistrationStates
from app.database import AsyncSessionFactory
from app.services.user_service import UserService
from app.services.audit_service import AuditService

router = Router()

WELCOME_NEW = (
    "👋 <b>Welcome to EscrowBot!</b>\n\n"
    "I'm a secure escrow service for crypto transactions.\n\n"
    "🔒 <b>How it works:</b>\n"
    "1. Buyer creates a deal and funds it\n"
    "2. Seller completes the work\n"
    "3. Buyer releases funds — or opens a dispute\n\n"
    "Let's set up your account. First, create a <b>4–8 digit PIN</b> "
    "to protect sensitive actions.\n\n"
    "Enter your PIN:"
)

WELCOME_BACK = (
    "👋 Welcome back, <b>{name}</b>!\n\n"
    "What would you like to do today?"
)

ANTI_PHISHING = (
    "\n\n⚠️ <b>Security reminder:</b> This bot will NEVER ask for your "
    "private keys or seed phrases. Report suspicious activity to @EscrowBotSupport."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return

    # Check for referral code in deep link
    args = message.text.split(maxsplit=1)
    referral_code = args[1].strip() if len(args) > 1 else None

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(tg_user.id)

        if not user:
            # New user — store referral in FSM, ask for PIN
            await state.update_data(
                referral_code=referral_code,
                tg_first_name=tg_user.first_name,
                tg_last_name=tg_user.last_name,
                tg_username=tg_user.username,
                tg_lang=tg_user.language_code or "en",
            )
            await state.set_state(RegistrationStates.waiting_for_pin)
            await message.answer(WELCOME_NEW + ANTI_PHISHING, parse_mode="HTML")
        else:
            await message.answer(
                WELCOME_BACK.format(name=tg_user.first_name) + ANTI_PHISHING,
                reply_markup=main_menu_kb(),
                parse_mode="HTML",
            )


@router.message(RegistrationStates.waiting_for_pin)
async def reg_set_pin(message: Message, state: FSMContext) -> None:
    pin = message.text.strip() if message.text else ""
    # Delete the message immediately (PIN should not linger in chat)
    try:
        await message.delete()
    except Exception:
        pass

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await message.answer("❌ PIN must be 4–8 digits. Try again:")
        return

    await state.update_data(pin=pin)
    await state.set_state(RegistrationStates.confirm_pin)
    await message.answer("✅ Got it. Re-enter your PIN to confirm:")


@router.message(RegistrationStates.confirm_pin)
async def reg_confirm_pin(message: Message, state: FSMContext) -> None:
    confirm = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    if confirm != data.get("pin"):
        await state.set_state(RegistrationStates.waiting_for_pin)
        await message.answer("❌ PINs don't match. Enter your PIN again:")
        return

    # Create the user
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
        await svc.set_pin(user, data["pin"])
        await audit.pin_set(user.id)
        await session.commit()

    await state.clear()
    await message.answer(
        f"🎉 <b>Account created!</b>\n\n"
        f"Your referral code: <code>{user.referral_code}</code>\n\n"
        f"You're all set. Explore the menu below.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        f"🏠 <b>Main Menu</b>",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    text = (
        "ℹ️ <b>EscrowBot Help</b>\n\n"
        "<b>Creating a deal:</b>\n"
        "→ Tap 'New Deal', enter seller's username and deal details.\n\n"
        "<b>Paying for a deal:</b>\n"
        "→ After seller accepts, fund the escrow wallet shown.\n\n"
        "<b>Releasing funds:</b>\n"
        "→ When satisfied, tap 'Release Funds' to pay the seller.\n\n"
        "<b>Disputes:</b>\n"
        "→ If issues arise, tap 'Open Dispute'. Upload evidence.\n"
        "→ A moderator will review within 24–48 hours.\n\n"
        "<b>Security:</b>\n"
        "→ Never share your PIN.\n"
        "→ This bot never asks for private keys.\n\n"
        "Support: @EscrowBotSupport"
    )
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await callback.answer()
