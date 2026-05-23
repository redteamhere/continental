"""Registration and main menu."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.main_menu import main_menu_kb, back_kb
from app.bot.keyboards.pin_kb import pin_dots, pin_pad_kb, pin_webapp_kb, pin_remove_kb
from app.bot.handlers.pin_input import build_pin_message
from app.config import settings as _settings
from app.bot.states.registration import RegistrationStates
from app.bot.states.pin_reset import PinResetStates
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
    "⚠️ <b>Security reminder:</b> This bot will NEVER ask for your "
    "private keys or seed phrases."
)

WELCOME_BACK = (
    "👋 Welcome back, <b>{name}</b>!\n\n"
    "What would you like to do today?"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return

    args = message.text.split(maxsplit=1)
    referral_code = args[1].strip() if len(args) > 1 else None

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(tg_user.id)

        if not user:
            await state.update_data(
                referral_code=referral_code,
                tg_first_name=tg_user.first_name,
                tg_last_name=tg_user.last_name,
                tg_username=tg_user.username,
                tg_lang=tg_user.language_code or "en",
                pin_buffer="",
            )
            await state.set_state(RegistrationStates.waiting_for_pin)
            await message.answer(WELCOME_NEW, parse_mode="HTML")
            if _settings.WEB_APP_URL:
                await message.answer(
                    "🔐 <b>Create your PIN</b>\n\nTap the button below to set a secure 4–8 digit PIN.",
                    reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
                    parse_mode="HTML",
                )
            else:
                text, kb = build_pin_message(RegistrationStates.waiting_for_pin.state, 0)
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
        elif not user.pin_hash:
            # Existing user with no PIN — use PinResetStates so webapp routes to set_pin, not create
            await state.update_data(pin_buffer="")
            await state.set_state(PinResetStates.waiting_for_new_pin)
            if _settings.WEB_APP_URL:
                await message.answer(
                    "🔑 <b>PIN Required</b>\n\n"
                    "Your PIN was reset. Please set a new PIN to continue using the bot.",
                    reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
                    parse_mode="HTML",
                )
            else:
                text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
                await message.answer(
                    "🔑 <b>Your PIN was reset.</b> Please create a new PIN.\n\n"
                    + text.split("\n\n", 1)[-1],
                    reply_markup=kb,
                    parse_mode="HTML",
                )
        else:
            await message.answer(
                WELCOME_BACK.format(name=tg_user.first_name),
                reply_markup=main_menu_kb(),
                parse_mode="HTML",
            )


# ── PIN pad submit handlers (registration) ───────────────────────────────────

@router.callback_query(F.data == "pin:submit", RegistrationStates.waiting_for_pin)
async def reg_pin_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await callback.answer("Enter a 4–8 digit PIN.", show_alert=True)
        return

    await state.update_data(pin=pin, pin_buffer="")
    await state.set_state(RegistrationStates.confirm_pin)

    text, kb = build_pin_message(RegistrationStates.confirm_pin.state, 0)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pin:submit", RegistrationStates.confirm_pin)
async def reg_pin_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    confirm = data.get("pin_buffer", "")

    if confirm != data.get("pin"):
        # Reset back to entry step
        await state.update_data(pin_buffer="")
        await state.set_state(RegistrationStates.waiting_for_pin)
        text, kb = build_pin_message(RegistrationStates.waiting_for_pin.state, 0)
        await callback.message.edit_text(
            "❌ PINs don't match. Create a new PIN:\n\n"
            + text.split("\n\n", 1)[-1],
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)

        user = await svc.create(
            telegram_id=callback.from_user.id,
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
    await callback.message.edit_text(
        f"🎉 <b>Account created!</b>\n\n"
        f"Your referral code: <code>{user.referral_code}</code>\n\n"
        f"You're all set. Explore the menu below.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Main menu ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Main Menu</b>",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("myid"))
async def cmd_myid(message: Message, db_user) -> None:
    is_admin = message.from_user.id in _settings.ADMIN_IDS
    role = db_user.role.value if db_user else "not registered"
    await message.answer(
        f"🪪 Your Telegram ID: <code>{message.from_user.id}</code>\n"
        f"DB role: <b>{role}</b>\n"
        f"In ADMIN_IDS: <b>{'yes ✅' if is_admin else 'no ❌'}</b>\n"
        f"ADMIN_IDS configured: <code>{_settings.ADMIN_IDS}</code>",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(_HELP_TEXT, reply_markup=back_kb(), parse_mode="HTML")
    await callback.answer()


_HELP_TEXT = (
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
