"""User profile, stats, and PIN management."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.pin_input import build_pin_message
from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot.keyboards.pin_kb import pin_webapp_kb
from app.bot.states.pin import PinStates
from app.bot.states.pin_reset import PinResetStates
from app.config import settings as _settings
from app.database import AsyncSessionFactory
from app.services.audit_service import AuditService
from app.services.user_service import UserService
from app.security.pin_manager import PinManager

router = Router()


def _profile_text(user) -> str:
    lock_icon = "🔒" if user.pin_hash else "⚠️ No PIN set"
    role_icon = {"admin": "👑", "moderator": "🛡️", "user": "👤"}.get(user.role.value, "👤")
    return (
        f"{role_icon} <b>Your Profile</b>\n\n"
        f"Name: {user.first_name} {user.last_name or ''}\n"
        f"Username: @{user.username or 'not set'}\n"
        f"Member since: {user.created_at.strftime('%d %b %Y')}\n\n"
        f"<b>Statistics</b>\n"
        f"📊 Total Deals: {user.total_deals}\n"
        f"🛒 Purchases: {user.total_purchases}\n"
        f"💼 Sales: {user.total_sales}\n"
        f"⭐ Reputation: {user.reputation_score:.1f}/5.0\n\n"
        f"<b>Referral</b>\n"
        f"🔗 Your code: <code>{user.referral_code}</code>\n\n"
        f"<b>Security</b>\n"
        f"PIN: {lock_icon}"
    )


from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton


def profile_kb(has_pin: bool, lang: str = "en") -> object:
    from app.i18n.translations import t
    builder = InlineKeyboardBuilder()
    if has_pin:
        builder.row(InlineKeyboardButton(text="🔑 Change PIN", callback_data="profile:change_pin"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 Set PIN", callback_data="profile:set_pin"))
    builder.row(InlineKeyboardButton(text=t("btn_language", lang), callback_data="profile:language"))
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu:main"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first with /start", show_alert=True)
        return
    from app.i18n.translations import get_lang
    lang = get_lang(db_user)
    await callback.message.edit_text(
        _profile_text(db_user),
        reply_markup=profile_kb(bool(db_user.pin_hash), lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:stats")
async def show_stats(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select, func
        from app.models.audit import Review
        from app.database import AsyncSessionFactory

        svc = UserService(session)
        await svc.recalculate_reputation(db_user)
        await session.commit()

    text = (
        f"📊 <b>Your Statistics</b>\n\n"
        f"Total Deals: <b>{db_user.total_deals}</b>\n"
        f"Purchases: <b>{db_user.total_purchases}</b>\n"
        f"Sales: <b>{db_user.total_sales}</b>\n"
        f"Disputes Opened: <b>{db_user.total_disputes_opened}</b>\n"
        f"Disputes Won: <b>{db_user.total_disputes_won}</b>\n\n"
        f"⭐ Reputation: <b>{db_user.reputation_score:.1f}</b>/5.0"
    )
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "menu:referral")
async def show_referral(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first.", show_alert=True)
        return

    bot_username = (await callback.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={db_user.referral_code}"
    text = (
        f"🔗 <b>Referral Program</b>\n\n"
        f"Share your link and earn <b>{0.1:.1f}% bonus</b> on each deal "
        f"your referrals make.\n\n"
        f"Your code: <code>{db_user.referral_code}</code>\n"
        f"Your link: {link}"
    )
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await callback.answer()


# ── PIN management ───────────────────────────────────────────

@router.callback_query(F.data == "profile:set_pin")
async def start_set_pin(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not db_user:
        return
    await state.update_data(pin_buffer="")
    await state.set_state(PinResetStates.waiting_for_new_pin)
    if _settings.WEB_APP_URL:
        await callback.message.answer(
            "🔑 <b>Set your PIN</b>\n\nTap the button below to set a 4–8 digit PIN.",
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "profile:change_pin")
async def start_change_pin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pin_buffer="")
    await state.set_state(PinStates.change_old)
    if _settings.WEB_APP_URL:
        await callback.message.answer(
            "🔐 <b>Change PIN</b>\n\nFirst, enter your <b>current</b> PIN to verify it's you.",
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "verify"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinStates.change_old.state, 0)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pin:submit", PinStates.change_old)
async def change_pin_verify_old(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await callback.answer("Enter your current PIN first.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)
        ok = await svc.verify_pin(user, pin)
        if not ok:
            await audit.pin_failed(user.id)
            await session.commit()
            await state.update_data(pin_buffer="")
            text, kb = build_pin_message(PinStates.change_old.state, 0)
            await callback.message.edit_text(
                "❌ Wrong PIN. Try again:\n\n" + text.split("\n\n", 1)[-1],
                reply_markup=kb,
                parse_mode="HTML",
            )
            await callback.answer()
            return
        await session.commit()

    await state.update_data(pin_buffer="")
    await state.set_state(PinResetStates.waiting_for_new_pin)
    if _settings.WEB_APP_URL:
        await callback.message.edit_text(
            "✅ Verified. Now set your new PIN.",
            parse_mode="HTML",
        )
        await callback.message.answer(
            "🔑 <b>New PIN</b>\n\nTap the button to set your new PIN.",
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
