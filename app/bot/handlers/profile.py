"""User profile (photo card), stats, referral, and PIN management."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, join, select

from app.bot.handlers.pin_input import build_pin_message
from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot.keyboards.pin_kb import pin_webapp_kb
from app.bot.states.pin import PinStates
from app.bot.states.pin_reset import PinResetStates
from app.config import settings as _settings
from app.database import AsyncSessionFactory
from app.i18n.translations import get_lang, t
from app.models.deal import Deal, DealStatus
from app.models.wallet import Wallet
from app.services.audit_service import AuditService
from app.services.profile_card import generate_profile_card
from app.services.user_service import UserService
from app.security.pin_manager import PinManager

router = Router()


# ── Helpers ───────────────────────────────────────────────────────────────────

def profile_kb(has_pin: bool, lang: str = "en"):
    builder = InlineKeyboardBuilder()
    if has_pin:
        builder.row(InlineKeyboardButton(
            text=t("btn_change_pin", lang), callback_data="profile:change_pin"
        ))
    else:
        builder.row(InlineKeyboardButton(
            text=t("btn_set_pin", lang), callback_data="profile:set_pin"
        ))
    builder.row(
        InlineKeyboardButton(text=t("btn_stats", lang),    callback_data="menu:stats"),
        InlineKeyboardButton(text=t("btn_referral", lang), callback_data="menu:referral"),
    )
    builder.row(InlineKeyboardButton(
        text=t("btn_language", lang), callback_data="profile:language"
    ))
    builder.row(InlineKeyboardButton(
        text=t("btn_back", lang), callback_data="menu:main"
    ))
    return builder.as_markup()


async def _get_escrow_balance(user_id: int) -> Decimal:
    """Sum confirmed_balance of escrow wallets for the user's active funded deals."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(Wallet.confirmed_balance), Decimal("0")))
            .select_from(join(Wallet, Deal, Deal.escrow_wallet_id == Wallet.id))
            .where(
                Deal.buyer_id == user_id,
                Deal.status.in_([DealStatus.FUNDED, DealStatus.IN_PROGRESS]),
            )
        )
        return result.scalar_one() or Decimal("0")


async def _send_profile_card(callback: CallbackQuery, db_user) -> None:
    """Delete the triggering message and send the profile photo card."""
    lang    = get_lang(db_user)
    balance = await _get_escrow_balance(db_user.id)

    role_icons = {"admin": "👑", "moderator": "🛡️", "user": "👤"}
    role_label  = t(f"role_{db_user.role.value}", lang)
    role_icon   = role_icons.get(db_user.role.value, "👤")
    full_name   = f"{db_user.first_name} {db_user.last_name or ''}".strip()
    username    = db_user.username or ""
    deposit_str = f"${balance:.2f}"

    # Generate card image in a thread pool (PIL is blocking)
    card_bytes = await asyncio.to_thread(
        generate_profile_card,
        username,
        full_name,
        deposit_str,
        f"{role_icon} {role_label}",
        t("profile_deposit", lang),      # localised "Deposit" / "Депозит" etc.
    )

    # Build multilingual caption
    caption = t(
        "profile_caption",
        lang,
        username=username or full_name,
        tg_id=db_user.telegram_id,
        full_name=full_name,
        role=f"{role_icon} {role_label}",
        reputation=f"{db_user.reputation_score:.1f}",
        deposit=deposit_str,
        purchases=db_user.total_purchases,
        sales=db_user.total_sales,
        referral_code=db_user.referral_code,
    )

    # Delete old menu message (ignore errors — may already be deleted)
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send the new profile photo
    await callback.bot.send_photo(
        chat_id=callback.from_user.id,
        photo=BufferedInputFile(card_bytes.read(), filename="profile.jpg"),
        caption=caption,
        reply_markup=profile_kb(bool(db_user.pin_hash), lang),
        parse_mode="HTML",
    )


# ── Profile page ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first with /start", show_alert=True)
        return
    await _send_profile_card(callback, db_user)
    await callback.answer()


# ── Statistics page ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:stats")
async def show_stats(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first.", show_alert=True)
        return
    lang = get_lang(db_user)

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        await svc.recalculate_reputation(db_user)
        await session.commit()

    text = (
        f"{t('stats_title', lang)}\n\n"
        f"{t('stats_total_deals', lang)}: <b>{db_user.total_deals}</b>\n"
        f"{t('stats_purchases', lang)}: <b>{db_user.total_purchases}</b>\n"
        f"{t('stats_sales', lang)}: <b>{db_user.total_sales}</b>\n"
        f"{t('stats_disputes_open', lang)}: <b>{db_user.total_disputes_opened}</b>\n"
        f"{t('stats_disputes_won', lang)}: <b>{db_user.total_disputes_won}</b>\n\n"
        f"{t('stats_reputation', lang)}: <b>{db_user.reputation_score:.1f}</b>/5.0"
    )
    # Work whether current message is text or photo
    try:
        await callback.message.edit_text(
            text, reply_markup=back_kb("menu:profile", lang=lang), parse_mode="HTML"
        )
    except Exception:
        try:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=back_kb("menu:profile", lang=lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer()


# ── Referral page ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:referral")
async def show_referral(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first.", show_alert=True)
        return
    lang = get_lang(db_user)

    bot_username = (await callback.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={db_user.referral_code}"
    text = (
        f"{t('referral_title', lang)}\n\n"
        f"{t('referral_desc', lang, bonus=0.1)}\n\n"
        f"{t('referral_your_code', lang)}: <code>{db_user.referral_code}</code>\n"
        f"{t('referral_your_link', lang)}: {link}"
    )
    try:
        await callback.message.edit_text(
            text, reply_markup=back_kb("menu:profile", lang=lang), parse_mode="HTML"
        )
    except Exception:
        try:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=back_kb("menu:profile", lang=lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer()


# ── Language picker (from profile) ───────────────────────────────────────────

@router.callback_query(F.data == "profile:language")
async def change_language_menu(callback: CallbackQuery, db_user) -> None:
    from app.bot.keyboards.lang_kb import language_select_kb
    lang = get_lang(db_user)
    text = t("choose_language", lang)
    try:
        await callback.message.edit_text(
            text, reply_markup=language_select_kb(), parse_mode="HTML"
        )
    except Exception:
        try:
            await callback.message.edit_caption(
                caption=text, reply_markup=language_select_kb(), parse_mode="HTML"
            )
        except Exception:
            pass
    await callback.answer()


# ── PIN management ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "profile:set_pin")
async def start_set_pin(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not db_user:
        return
    lang = get_lang(db_user)
    await state.update_data(pin_buffer="")
    await state.set_state(PinResetStates.waiting_for_new_pin)
    if _settings.WEB_APP_URL:
        await callback.message.answer(
            t("pin_set_title", lang),
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "profile:change_pin")
async def start_change_pin(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    lang = get_lang(db_user)
    await state.update_data(pin_buffer="")
    await state.set_state(PinStates.change_old)
    if _settings.WEB_APP_URL:
        await callback.message.answer(
            t("pin_change_title", lang),
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
    pin  = data.get("pin_buffer", "")

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await callback.answer("Enter your current PIN first.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        svc   = UserService(session)
        audit = AuditService(session)
        user  = await svc.get_by_telegram_id(callback.from_user.id)
        lang  = get_lang(user)
        ok    = await svc.verify_pin(user, pin)
        if not ok:
            await audit.pin_failed(user.id)
            await session.commit()
            await state.update_data(pin_buffer="")
            text, kb = build_pin_message(PinStates.change_old.state, 0)
            await callback.message.edit_text(
                t("pin_wrong", lang) + "\n\n" + text.split("\n\n", 1)[-1],
                reply_markup=kb,
                parse_mode="HTML",
            )
            await callback.answer()
            return
        await session.commit()

    await state.update_data(pin_buffer="")
    await state.set_state(PinResetStates.waiting_for_new_pin)
    if _settings.WEB_APP_URL:
        await callback.message.edit_text(t("pin_verified", lang), parse_mode="HTML")
        await callback.message.answer(
            t("pin_new_title", lang),
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
