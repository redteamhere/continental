"""Registration, language selection, and main menu."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.lang_kb import language_select_kb
from app.bot.keyboards.main_menu import main_menu_kb, back_kb
from app.bot.keyboards.pin_kb import pin_webapp_kb
from app.bot.handlers.pin_input import build_pin_message
from app.config import settings as _settings
from app.bot.states.registration import RegistrationStates
from app.bot.states.pin_reset import PinResetStates
from app.database import AsyncSessionFactory
from app.i18n.translations import t, get_lang
from app.services.user_service import UserService
from app.services.audit_service import AuditService

router = Router()


# ── /start ───────────────────────────────────────────────────────────────────

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
            # ── New user: save referral/tg data, show language picker ──────
            await state.update_data(
                referral_code=referral_code,
                tg_first_name=tg_user.first_name,
                tg_last_name=tg_user.last_name,
                tg_username=tg_user.username,
                tg_lang=tg_user.language_code or "en",
                pin_buffer="",
            )
            await state.set_state(RegistrationStates.select_language)
            await message.answer(
                "🌍 <b>Welcome to EscrowBot!</b>\n\nPlease choose your language:\n"
                "请选择语言 / Выберите язык / Escolha o idioma / Dil seçin",
                reply_markup=language_select_kb(),
                parse_mode="HTML",
            )

        elif not user.pin_hash:
            # ── Existing user with no PIN (admin reset) ────────────────────
            lang = get_lang(user)
            await state.update_data(pin_buffer="")
            await state.set_state(PinResetStates.waiting_for_new_pin)
            if _settings.WEB_APP_URL:
                await message.answer(
                    t("pin_reset", lang),
                    reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
                    parse_mode="HTML",
                )
            else:
                text, kb = build_pin_message(PinResetStates.waiting_for_new_pin.state, 0)
                await message.answer(
                    t("pin_reset", lang) + "\n\n" + text.split("\n\n", 1)[-1],
                    reply_markup=kb,
                    parse_mode="HTML",
                )

        else:
            # ── Returning user ─────────────────────────────────────────────
            lang = get_lang(user)
            monthly = await svc.count_monthly_active()
            await message.answer(
                t("welcome_back", lang, name=tg_user.first_name)
                + f"\n\n👥 <b>{monthly:,}</b> monthly active users",
                reply_markup=main_menu_kb(lang),
                parse_mode="HTML",
            )


# ── Language selection (new user registration flow) ──────────────────────────

@router.callback_query(F.data.startswith("lang:"), RegistrationStates.select_language)
async def select_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":")[1]   # e.g. "en", "zh", "ru", "pt", "tr"
    await state.update_data(selected_lang=lang)
    await state.set_state(RegistrationStates.waiting_for_pin)

    # Show welcome + PIN creation in chosen language
    await callback.message.edit_text(
        t("welcome_new", lang),
        parse_mode="HTML",
    )
    if _settings.WEB_APP_URL:
        await callback.message.answer(
            t("create_pin", lang),
            reply_markup=pin_webapp_kb(_settings.WEB_APP_URL, "set"),
            parse_mode="HTML",
        )
    else:
        text, kb = build_pin_message(RegistrationStates.waiting_for_pin.state, 0)
        await callback.message.answer(
            t("create_pin", lang) + "\n\n" + text.split("\n\n", 1)[-1],
            reply_markup=kb,
            parse_mode="HTML",
        )
    await callback.answer()


# ── Language selection for existing users (lang:XX callback, no FSM state) ───
# NOTE: profile:language handler lives in profile.py (handles photo messages).

@router.callback_query(F.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, db_user) -> None:
    """Save the chosen language and refresh the current view."""
    if not db_user:
        await callback.answer("Please /start first.", show_alert=True)
        return
    new_lang = callback.data.split(":")[1]

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)
        if user:
            user.language_code = new_lang
            await session.commit()

    # Update the in-memory object so subsequent code sees the new language
    db_user.language_code = new_lang

    # If it's a plain text message (e.g. registration flow) → edit in place
    try:
        await callback.message.edit_text(
            t("language_changed", new_lang),
            reply_markup=main_menu_kb(new_lang),
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception:
        # Came from the profile photo — resend the profile card in the new language
        from app.bot.handlers.profile import _send_profile_card
        await _send_profile_card(callback, db_user)
        await callback.answer(t("language_changed", new_lang))


# ── PIN pad submit handlers (registration) ───────────────────────────────────

@router.callback_query(F.data == "pin:submit", RegistrationStates.waiting_for_pin)
async def reg_pin_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")
    lang = data.get("selected_lang", "en")

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
    lang = data.get("selected_lang", "en")

    if confirm != data.get("pin"):
        await state.update_data(pin_buffer="")
        await state.set_state(RegistrationStates.waiting_for_pin)
        text, kb = build_pin_message(RegistrationStates.waiting_for_pin.state, 0)
        await callback.message.edit_text(
            "❌ PINs don't match. Create a new PIN:\n\n" + text.split("\n\n", 1)[-1],
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
            language_code=lang,
            referral_code_used=data.get("referral_code"),
        )
        await svc.set_pin(user, data["pin"])
        await audit.pin_set(user.id)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        t("account_created", lang, referral_code=user.referral_code),
        reply_markup=main_menu_kb(lang),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Main menu ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    await state.clear()
    lang = get_lang(db_user)
    menu_text = "🏠 <b>Main Menu</b>"
    kb = main_menu_kb(lang)
    # edit_text fails on photo messages — fall back to delete + resend
    try:
        await callback.message.edit_text(menu_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.bot.send_message(
            callback.from_user.id, menu_text, reply_markup=kb, parse_mode="HTML"
        )
    await callback.answer()


# ── /myid debug command ───────────────────────────────────────────────────────

@router.message(Command("myid"))
async def cmd_myid(message: Message, db_user) -> None:
    is_admin = message.from_user.id in _settings.ADMIN_IDS
    role = db_user.role.value if db_user else "not registered"
    lang = get_lang(db_user)
    await message.answer(
        f"🪪 Your Telegram ID: <code>{message.from_user.id}</code>\n"
        f"DB role: <b>{role}</b>\n"
        f"Language: <b>{lang}</b>\n"
        f"In ADMIN_IDS: <b>{'yes ✅' if is_admin else 'no ❌'}</b>\n"
        f"ADMIN_IDS configured: <code>{_settings.ADMIN_IDS}</code>",
        parse_mode="HTML",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message, db_user) -> None:
    lang = get_lang(db_user)
    await message.answer(_help_text(lang), parse_mode="HTML")


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery, db_user) -> None:
    lang = get_lang(db_user)
    await callback.message.edit_text(
        _help_text(lang),
        reply_markup=back_kb(lang=lang),
        parse_mode="HTML",
    )
    await callback.answer()


def _help_text(lang: str = "en") -> str:
    texts = {
        "en": (
            "ℹ️ <b>EscrowBot Help</b>\n\n"
            "<b>Creating a deal:</b>\n→ Tap 'New Deal', enter seller's username and details.\n\n"
            "<b>Paying for a deal:</b>\n→ After seller accepts, fund the escrow wallet shown.\n\n"
            "<b>Releasing funds:</b>\n→ When satisfied, tap 'Release Funds' to pay the seller.\n\n"
            "<b>Disputes:</b>\n→ Tap 'Open Dispute' if issues arise. A moderator reviews within 24–48h.\n\n"
            "<b>Security:</b>\n→ Never share your PIN. This bot never asks for private keys.\n\n"
            "Support: @EscrowBotSupport"
        ),
        "zh": (
            "ℹ️ <b>EscrowBot 帮助</b>\n\n"
            "<b>创建交易：</b>\n→ 点击「新交易」，输入卖家用户名及详情。\n\n"
            "<b>为交易付款：</b>\n→ 卖家接受后，向显示的担保钱包转账。\n\n"
            "<b>释放资金：</b>\n→ 满意后点击「释放资金」支付给卖家。\n\n"
            "<b>争议：</b>\n→ 如有问题，点击「发起争议」，审核员将在 24–48 小时内处理。\n\n"
            "<b>安全：</b>\n→ 请勿分享您的 PIN，本机器人绝不索要私钥。\n\n"
            "支持：@EscrowBotSupport"
        ),
        "ru": (
            "ℹ️ <b>Помощь EscrowBot</b>\n\n"
            "<b>Создание сделки:</b>\n→ Нажмите «Новая сделка», введите имя продавца и детали.\n\n"
            "<b>Оплата сделки:</b>\n→ После принятия продавцом пополните показанный кошелёк.\n\n"
            "<b>Освобождение средств:</b>\n→ Нажмите «Освободить средства», когда будете довольны.\n\n"
            "<b>Споры:</b>\n→ Нажмите «Открыть спор» при проблемах. Модератор ответит за 24–48ч.\n\n"
            "<b>Безопасность:</b>\n→ Не делитесь PIN. Бот никогда не запрашивает приватные ключи.\n\n"
            "Поддержка: @EscrowBotSupport"
        ),
        "pt": (
            "ℹ️ <b>Ajuda EscrowBot</b>\n\n"
            "<b>Criando um negócio:</b>\n→ Toque em 'Novo Negócio', insira o usuário do vendedor e detalhes.\n\n"
            "<b>Pagando um negócio:</b>\n→ Após o vendedor aceitar, financie a carteira de garantia exibida.\n\n"
            "<b>Liberando fundos:</b>\n→ Quando satisfeito, toque em 'Liberar Fundos' para pagar o vendedor.\n\n"
            "<b>Disputas:</b>\n→ Toque em 'Abrir Disputa' se houver problemas. Um moderador revisa em 24–48h.\n\n"
            "<b>Segurança:</b>\n→ Nunca compartilhe seu PIN. Este bot nunca pede chaves privadas.\n\n"
            "Suporte: @EscrowBotSupport"
        ),
        "tr": (
            "ℹ️ <b>EscrowBot Yardım</b>\n\n"
            "<b>Anlaşma oluşturma:</b>\n→ 'Yeni Anlaşma'ya dokunun, satıcının kullanıcı adını ve detayları girin.\n\n"
            "<b>Anlaşma ödemesi:</b>\n→ Satıcı kabul ettikten sonra gösterilen emanet cüzdanı fonlayın.\n\n"
            "<b>Fonları serbest bırakma:</b>\n→ Memnun olduğunuzda satıcıya ödeme yapmak için 'Fonları Serbest Bırak'a dokunun.\n\n"
            "<b>Uyuşmazlıklar:</b>\n→ Sorun çıkarsa 'Uyuşmazlık Aç'a dokunun. Moderatör 24–48 saatte inceler.\n\n"
            "<b>Güvenlik:</b>\n→ PIN'inizi asla paylaşmayın. Bu bot hiçbir zaman özel anahtar istemez.\n\n"
            "Destek: @EscrowBotSupport"
        ),
    }
    return texts.get(lang, texts["en"])
