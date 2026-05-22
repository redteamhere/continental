"""User profile, stats, and PIN management."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot.states.pin import PinStates
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


def profile_kb(has_pin: bool) -> object:
    builder = InlineKeyboardBuilder()
    if has_pin:
        builder.row(InlineKeyboardButton(text="🔑 Change PIN", callback_data="profile:change_pin"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 Set PIN", callback_data="profile:set_pin"))
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="menu:main"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first with /start", show_alert=True)
        return
    await callback.message.edit_text(
        _profile_text(db_user),
        reply_markup=profile_kb(bool(db_user.pin_hash)),
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
    await state.set_state(PinStates.set_new)
    await callback.message.answer("Enter your new 4–8 digit PIN:")
    await callback.answer()


@router.message(PinStates.set_new)
async def pin_set_new(message: Message, state: FSMContext, db_user) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await message.answer("❌ PIN must be 4–8 digits.")
        return
    await state.update_data(new_pin=pin)
    await state.set_state(PinStates.confirm_new)
    await message.answer("Re-enter the PIN to confirm:")


@router.message(PinStates.confirm_new)
async def pin_confirm_new(message: Message, state: FSMContext, db_user) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    if pin != data.get("new_pin"):
        await state.set_state(PinStates.set_new)
        await message.answer("❌ PINs don't match. Start over:")
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)
        await svc.set_pin(user, pin)
        await audit.pin_set(user.id)
        await session.commit()

    await state.clear()
    await message.answer("✅ PIN set successfully!", reply_markup=main_menu_kb())


@router.callback_query(F.data == "profile:change_pin")
async def start_change_pin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PinStates.change_old)
    await callback.message.answer("Enter your current PIN:")
    await callback.answer()


@router.message(PinStates.change_old)
async def pin_change_verify_old(message: Message, state: FSMContext) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)
        ok = await svc.verify_pin(user, pin)
        if not ok:
            await audit.pin_failed(user.id)
            await session.commit()
            remaining = 5 - user.pin_attempts if user.pin_attempts < 5 else 0
            await message.answer(f"❌ Wrong PIN. {remaining} attempts remaining.")
            return
        await session.commit()

    await state.set_state(PinStates.change_new)
    await message.answer("Enter your new PIN:")


@router.message(PinStates.change_new)
async def pin_change_new(message: Message, state: FSMContext) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await message.answer("❌ PIN must be 4–8 digits.")
        return
    await state.update_data(new_pin=pin)
    await state.set_state(PinStates.change_confirm)
    await message.answer("Confirm your new PIN:")


@router.message(PinStates.change_confirm)
async def pin_change_confirm(message: Message, state: FSMContext) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    if pin != data.get("new_pin"):
        await state.set_state(PinStates.change_new)
        await message.answer("❌ PINs don't match. Enter new PIN again:")
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)
        await svc.set_pin(user, pin)
        await audit.pin_set(user.id)
        await session.commit()

    await state.clear()
    await message.answer("✅ PIN changed successfully!", reply_markup=main_menu_kb())
