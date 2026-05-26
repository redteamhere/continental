"""User profile, stats, PIN management — fully translated."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.bot.handlers.pin_input import build_pin_message
from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot.keyboards.pin_kb import pin_webapp_kb
from app.bot.states.pin import PinStates
from app.bot.states.pin_reset import PinResetStates
from app.config import settings as _settings
from app.database import AsyncSessionFactory
from app.i18n.translations import t, get_lang
from app.services.audit_service import AuditService
from app.services.user_service import UserService
from app.security.pin_manager import PinManager

router = Router()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _profile_text(user, lang: str = "en") -> str:
    role_icons = {"admin": "👑", "moderator": "🛡️", "user": "👤"}
    role_icon = role_icons.get(user.role.value, "👤")
    role_label = t(f"role_{user.role.value}", lang)

    pin_status = "🔒" if user.pin_hash else t("profile_no_pin", lang)
    username = f"@{user.username}" if user.username else "—"
    full_name = f"{user.first_name} {user.last_name or ''}".strip()

    return (
        f"{role_icon} <b>{t('profile_title', lang)}</b> — {role_label}\n\n"
        f"<b>{t('profile_name', lang)}:</b> {full_name}\n"
        f"<b>{t('profile_username', lang)}:</b> {username}\n"
        f"<b>{t('profile_member_since', lang)}:</b> {user.created_at.strftime('%d %b %Y')}\n\n"
        f"<b>{t('profile_stats', lang)}</b>\n"
        f"📊 {t('profile_total_deals', lang)}: {user.total_deals}\n"
        f"🛒 {t('profile_purchases', lang)}: {user.total_purchases}\n"
        f"💼 {t('profile_sales', lang)}: {user.total_sales}\n"
        f"⭐ {t('profile_reputation', lang)}: {user.reputation_score:.1f}/5.0\n\n"
        f"<b>{t('profile_referral', lang)}</b>\n"
        f"🔗 {t('profile_your_code', lang)}: <code>{user.referral_code}</code>\n\n"
        f"<b>{t('profile_security', lang)}</b>\n"
        f"{t('profile_pin', lang)}: {pin_status}"
    )


def profile_kb(has_pin: bool, lang: str = "en") -> object:
    builder = InlineKeyboardBuilder()
    if has_pin:
        builder.row(InlineKeyboardButton(text=t("btn_change_pin", lang), callback_data="profile:change_pin"))
    else:
        builder.row(InlineKeyboardButton(text=t("btn_set_pin", lang), callback_data="profile:set_pin"))
    builder.row(InlineKeyboardButton(text=t("btn_language", lang), callback_data="profile:language"))
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu:main"))
    return builder.as_markup()


# ── Profile page ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please register first with /start", show_alert=True)
        return
    lang = get_lang(db_user)
    await callback.message.edit_text(
        _profile_text(db_user, lang),
        reply_markup=profile_kb(bool(db_user.pin_hash), lang),
        parse_mode="HTML",
    )
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
    await callback.message.edit_text(text, reply_markup=back_kb(lang=lang), parse_mode="HTML")
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
    await callback.message.edit_text(text, reply_markup=back_kb(lang=lang), parse_mode="HTML")
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
    pin = data.get("pin_buffer", "")

    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        await callback.answer("Enter your current PIN first.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)
        lang = get_lang(user)
        ok = await svc.verify_pin(user, pin)
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
