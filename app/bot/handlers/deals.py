"""Deal creation, viewing, acceptance, and fund release."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.deal_kb import (
    confirm_cancel_kb,
    currency_select_kb,
    deadline_select_kb,
    deal_action_kb,
    review_stars_kb,
)
from app.models.audit import Review
from app.bot.keyboards.main_menu import back_kb, deals_list_kb, main_menu_kb
from app.bot.keyboards.pin_kb import pin_pad_kb, pin_dots, pin_webapp_kb
from app.bot.handlers.pin_input import build_pin_message
from app.bot.states.deal_creation import DealCreationStates
from app.config import settings
from app.security.pin_manager import PinManager
from app.database import AsyncSessionFactory
from app.models.deal import Currency, DealStatus
from app.services.audit_service import AuditService
from app.services.deal_service import DealService
from app.services.escrow_service import EscrowService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


class ReleasePinState(StatesGroup):
    verify = State()


router = Router()


# ── Create deal flow ─────────────────────────────────────────

@router.callback_query(F.data == "menu:new_deal")
async def new_deal_start(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not db_user:
        await callback.answer("Please /start first.", show_alert=True)
        return
    if not db_user.pin_hash:
        await callback.answer("Set a PIN in your profile first.", show_alert=True)
        return

    await state.set_state(DealCreationStates.enter_seller)
    await callback.message.edit_text(
        "📋 <b>Create New Deal</b>\n\nStep 1/6: Enter the seller's <b>@username</b>:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DealCreationStates.enter_seller)
async def deal_enter_seller(message: Message, state: FSMContext, db_user) -> None:
    if not message.text:
        return
    username = message.text.strip().lstrip("@")

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        seller = await svc.get_by_username(username)

    if not seller:
        await message.answer("❌ User not found. Check the username and try again:")
        return
    if seller.telegram_id == message.from_user.id:
        await message.answer("❌ You can't create a deal with yourself.")
        return
    if seller.is_banned:
        await message.answer("❌ This user is unavailable.")
        return

    await state.update_data(seller_id=seller.id, seller_username=seller.username)
    await state.set_state(DealCreationStates.enter_description)
    await message.answer(
        f"✅ Seller: @{seller.username}\n\n"
        f"Step 2/6: Enter a <b>description</b> of what you're buying (max 500 chars):",
        parse_mode="HTML",
    )


@router.message(DealCreationStates.enter_description)
async def deal_enter_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    desc = message.text.strip()
    if len(desc) < 10:
        await message.answer("❌ Description too short (min 10 characters).")
        return
    if len(desc) > 500:
        await message.answer("❌ Description too long (max 500 characters).")
        return

    await state.update_data(description=desc)
    await state.set_state(DealCreationStates.enter_amount)
    await message.answer("Step 3/6: Enter the <b>amount</b> (e.g. 150.00):", parse_mode="HTML")


@router.message(DealCreationStates.enter_amount)
async def deal_enter_amount(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid amount. Enter a positive number:")
        return

    await state.update_data(amount=str(amount))
    await state.set_state(DealCreationStates.select_currency)
    await message.answer("Step 4/6: Select the <b>currency</b>:", reply_markup=currency_select_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("currency:"))
async def deal_select_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_str = callback.data.split(":")[1]
    try:
        currency = Currency(currency_str)
    except ValueError:
        await callback.answer("Invalid currency", show_alert=True)
        return

    await state.update_data(currency=currency.value)
    await state.set_state(DealCreationStates.enter_deadline)
    await callback.message.edit_text(
        f"Currency: <b>{currency.symbol}</b>\n\nStep 5/6: Select the <b>deadline</b>:",
        reply_markup=deadline_select_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deadline:"))
async def deal_select_deadline(callback: CallbackQuery, state: FSMContext) -> None:
    days = int(callback.data.split(":")[1])
    await state.update_data(deadline_days=days)
    await state.set_state(DealCreationStates.enter_terms)
    await callback.message.edit_text(
        f"Deadline: <b>{days} day(s)</b>\n\n"
        f"Step 6/6: Enter <b>terms & conditions</b> (or type 'skip'):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DealCreationStates.enter_terms)
async def deal_enter_terms(message: Message, state: FSMContext) -> None:
    terms = None if message.text.strip().lower() == "skip" else message.text.strip()
    await state.update_data(terms=terms)
    await state.set_state(DealCreationStates.review_and_confirm)

    data = await state.get_data()
    amount = Decimal(data["amount"])
    fee = amount * Decimal(str(settings.ESCROW_FEE_PERCENT)) / Decimal("100")

    summary = (
        f"📋 <b>Deal Summary</b>\n\n"
        f"Seller: @{data['seller_username']}\n"
        f"Description: {data['description']}\n"
        f"Amount: <b>{amount} {data['currency']}</b>\n"
        f"Escrow fee ({settings.ESCROW_FEE_PERCENT}%): <b>{fee:.8f}</b>\n"
        f"Deadline: {data['deadline_days']} day(s)\n"
    )
    if terms:
        summary += f"Terms: {terms}\n"

    await state.update_data(pin_buffer="")
    await state.set_state(DealCreationStates.confirm_pin)
    await message.answer(summary, parse_mode="HTML")
    if settings.WEB_APP_URL:
        await message.answer(
            "🔐 <b>Enter PIN to confirm deal</b>",
            reply_markup=pin_webapp_kb(settings.WEB_APP_URL, "verify"),
            parse_mode="HTML",
        )
    else:
        pin_text, pin_kb = build_pin_message(DealCreationStates.confirm_pin.state, 0)
        await message.answer(pin_text, reply_markup=pin_kb, parse_mode="HTML")


@router.callback_query(F.data == "pin:submit", DealCreationStates.confirm_pin)
async def deal_pin_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)

        if PinManager.is_locked(user.pin_locked_until):
            secs = PinManager.seconds_until_unlock(user.pin_locked_until)
            await callback.message.edit_text(f"🔒 PIN locked. Try again in {secs // 60}m {secs % 60}s.")
            await state.clear()
            await callback.answer()
            return

        ok = await svc.verify_pin(user, pin)
        if not ok:
            await audit.pin_failed(user.id)
            await session.commit()
            await state.update_data(pin_buffer="")
            pin_text, pin_kb = build_pin_message(DealCreationStates.confirm_pin.state, 0)
            await callback.message.edit_text(
                "❌ Wrong PIN. Try again:\n\n" + pin_text.split("\n\n", 1)[-1],
                reply_markup=pin_kb,
                parse_mode="HTML",
            )
            await callback.answer()
            return
        await session.commit()

    await callback.answer()
    await _finalize_deal_creation(callback, state)


async def _finalize_deal_creation(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Works with both Message (text flow) and CallbackQuery (PIN pad flow)."""
    data = await state.get_data()
    tg_id = event.from_user.id
    bot = event.bot
    send = event.message.answer if isinstance(event, CallbackQuery) else event.answer

    async with AsyncSessionFactory() as session:
        user_svc = UserService(session)
        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        notif_svc = NotificationService(session, bot)
        audit = AuditService(session)

        buyer = await user_svc.get_by_telegram_id(tg_id)
        seller = await user_svc.get_by_id(data["seller_id"])

        today_count = await deal_svc.count_today_deals(buyer)
        if today_count >= settings.MAX_DEALS_PER_DAY:
            await send("❌ Daily deal limit reached. Try again tomorrow.")
            await state.clear()
            return

        deal = await deal_svc.create(
            buyer=buyer,
            seller=seller,
            description=data["description"],
            amount=Decimal(data["amount"]),
            currency=Currency(data["currency"]),
            deadline_days=data["deadline_days"],
            terms=data.get("terms"),
        )

        wallet = await escrow_svc.create_escrow_wallet(deal)
        await deal_svc.attach_wallet(deal, wallet)

        await audit.deal_created(buyer.id, deal.id, {"deal_number": deal.deal_number})
        await notif_svc.deal_created(deal, buyer, seller)
        await session.commit()

    await state.clear()
    await send(
        f"✅ <b>Deal Created!</b>\n\n"
        f"Deal ID: <code>{deal.deal_number}</code>\n"
        f"Waiting for @{seller.username} to accept.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "deal:cancel_creation")
async def cancel_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Deal creation cancelled.", reply_markup=main_menu_kb())
    await callback.answer()


# ── View deals ───────────────────────────────────────────────

@router.callback_query(F.data == "menu:my_deals")
async def my_deals(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please /start first.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        deals = await deal_svc.get_user_deals(db_user, limit=10, offset=0)

    if not deals:
        await callback.message.edit_text(
            "📁 <b>My Deals</b>\n\nNo deals yet. Create your first deal!",
            reply_markup=back_kb(),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"📁 <b>My Deals</b> ({len(deals)} shown)",
            reply_markup=deals_list_kb(deals, page=0, total=len(deals)),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("deal:view:"))
async def view_deal(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        deal = await deal_svc.get_by_id(deal_id)

    if not deal or db_user.id not in (deal.buyer_id, deal.seller_id):
        await callback.answer("Deal not found.", show_alert=True)
        return

    is_buyer = deal.buyer_id == db_user.id
    role = "Buyer" if is_buyer else "Seller"
    other_id = deal.seller_id if is_buyer else deal.buyer_id

    async with AsyncSessionFactory() as session:
        other_user = await UserService(session).get_by_id(other_id)

    status_map = {
        "pending": "🟡 Pending seller acceptance",
        "awaiting_payment": "💳 Awaiting payment",
        "funded": "💰 Funded — in escrow",
        "in_progress": "⚙️ In Progress",
        "completed": "✅ Completed",
        "cancelled": "❌ Cancelled",
        "disputed": "⚖️ Under Dispute",
        "refunded": "↩️ Refunded",
    }

    text = (
        f"📋 <b>Deal {deal.deal_number}</b>\n\n"
        f"Your role: <b>{role}</b>\n"
        f"Counterpart: {other_user.display_name if other_user else 'Unknown'}\n"
        f"Status: {status_map.get(deal.status.value, deal.status.value)}\n"
        f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
        f"Fee: {deal.fee_amount} {deal.currency.symbol}\n"
        f"Description: {deal.description}\n"
    )
    if deal.terms:
        text += f"Terms: {deal.terms}\n"
    if deal.deadline:
        text += f"Deadline: {deal.deadline.strftime('%d %b %Y %H:%M UTC')}\n"
    if deal.cancellation_reason:
        text += f"Reason: {deal.cancellation_reason}\n"

    await callback.message.edit_text(
        text,
        reply_markup=deal_action_kb(deal, db_user.id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Seller accepts / declines ────────────────────────────────

@router.callback_query(F.data.startswith("deal:accept:"))
async def accept_deal(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        notif_svc = NotificationService(session, callback.bot)
        deal = await deal_svc.get_by_id(deal_id)

        if not deal or deal.seller_id != db_user.id:
            await callback.answer("Not authorized.", show_alert=True)
            return

        await deal_svc.accept_by_seller(deal, db_user)

        buyer_svc = UserService(session)
        buyer = await buyer_svc.get_by_id(deal.buyer_id)
        await notif_svc.deal_accepted(deal, buyer, db_user)
        await session.commit()

    await callback.message.edit_text(
        f"✅ <b>Deal Accepted!</b>\n\nDeal <code>{deal.deal_number}</code> is now active.\n"
        f"Waiting for buyer to fund the escrow wallet.",
        reply_markup=back_kb("menu:my_deals"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deal:decline:"))
async def decline_deal(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        notif_svc = NotificationService(session, callback.bot)
        deal = await deal_svc.get_by_id(deal_id)

        if not deal or deal.seller_id != db_user.id:
            await callback.answer("Not authorized.", show_alert=True)
            return

        await deal_svc.cancel(deal, db_user, reason="Declined by seller")
        buyer = await UserService(session).get_by_id(deal.buyer_id)
        await notif_svc.deal_cancelled(deal, buyer, db_user)
        await session.commit()

    await callback.message.edit_text(
        f"❌ Deal <code>{deal.deal_number}</code> declined.",
        reply_markup=back_kb("menu:my_deals"),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Buyer releases funds ─────────────────────────────────────

@router.callback_query(F.data.startswith("deal:release:"))
async def release_funds(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])
    await state.update_data(pending_release_deal_id=deal_id, pin_buffer="")
    await state.set_state(ReleasePinState.verify)

    if settings.WEB_APP_URL:
        await callback.message.answer(
            "🔐 <b>Enter PIN to release funds</b>",
            reply_markup=pin_webapp_kb(settings.WEB_APP_URL, "verify"),
            parse_mode="HTML",
        )
    else:
        pin_text, pin_kb = build_pin_message(ReleasePinState.verify.state, 0)
        await callback.message.answer(pin_text, reply_markup=pin_kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pin:submit", ReleasePinState.verify)
async def release_pin_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pin = data.get("pin_buffer", "")
    deal_id = data.get("pending_release_deal_id")

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(callback.from_user.id)

        if PinManager.is_locked(user.pin_locked_until):
            secs = PinManager.seconds_until_unlock(user.pin_locked_until)
            await callback.message.edit_text(f"🔒 PIN locked. Try again in {secs // 60}m {secs % 60}s.")
            await state.clear()
            await callback.answer()
            return

        ok = await svc.verify_pin(user, pin)
        if not ok:
            await AuditService(session).pin_failed(user.id)
            await session.commit()
            await state.update_data(pin_buffer="")
            pin_text, pin_kb = build_pin_message(ReleasePinState.verify.state, 0)
            await callback.message.edit_text(
                "❌ Wrong PIN. Try again:\n\n" + pin_text.split("\n\n", 1)[-1],
                reply_markup=pin_kb,
                parse_mode="HTML",
            )
            await callback.answer()
            return

        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        notif_svc = NotificationService(session, callback.bot)
        audit = AuditService(session)

        deal = await deal_svc.get_by_id(deal_id)
        if not deal or deal.buyer_id != user.id:
            await callback.message.edit_text("Deal not found.")
            await state.clear()
            await callback.answer()
            return

        await deal_svc.complete(deal, user)
        await escrow_svc.release_funds_to_seller(deal)

        seller = await UserService(session).get_by_id(deal.seller_id)
        await notif_svc.deal_completed(deal, user, seller)
        await audit.deal_completed(user.id, deal.id)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Funds Released!</b>\n\nDeal <code>{deal.deal_number}</code> is complete.\n"
        f"Please leave a review for the seller.",
        reply_markup=review_stars_kb(deal.id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Seller marks as delivered ────────────────────────────────

@router.callback_query(F.data.startswith("deal:delivered:"))
async def seller_mark_delivered(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        notif_svc = NotificationService(session, callback.bot)

        deal = await deal_svc.get_by_id(deal_id)
        if not deal or deal.seller_id != db_user.id:
            await callback.answer("Not authorized.", show_alert=True)
            return
        if deal.status != DealStatus.FUNDED:
            await callback.answer("Deal is not in funded status.", show_alert=True)
            return

        await deal_svc.start_progress(deal)

        buyer = await UserService(session).get_by_id(deal.buyer_id)
        await notif_svc.seller_delivered(deal, buyer, db_user)
        await session.commit()

    await callback.message.edit_text(
        f"📦 <b>Marked as Delivered</b>\n\n"
        f"Deal <code>{deal.deal_number}</code>\n"
        f"The buyer has been notified to release funds.",
        reply_markup=back_kb("menu:my_deals"),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Cancel deal ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("deal:cancel:"))
async def cancel_deal(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "Are you sure you want to cancel this deal?",
        reply_markup=confirm_cancel_kb(
            confirm_data=f"deal:cancel_confirm:{deal_id}",
            cancel_data=f"deal:view:{deal_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deal:cancel_confirm:"))
async def cancel_deal_confirm(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        notif_svc = NotificationService(session, callback.bot)
        audit = AuditService(session)
        deal = await deal_svc.get_by_id(deal_id)

        if not deal or db_user.id not in (deal.buyer_id, deal.seller_id):
            await callback.answer("Not authorized.", show_alert=True)
            return

        await deal_svc.cancel(deal, db_user, reason="Cancelled by user")
        buyer = await UserService(session).get_by_id(deal.buyer_id)
        seller = await UserService(session).get_by_id(deal.seller_id)
        await notif_svc.deal_cancelled(deal, buyer, seller)
        await audit.deal_cancelled(db_user.id, deal.id, "Cancelled by user")
        await session.commit()

    await callback.message.edit_text(
        f"❌ Deal <code>{deal.deal_number}</code> cancelled.",
        reply_markup=back_kb("menu:my_deals"),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Reviews ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("review:"))
async def submit_review(callback: CallbackQuery, db_user) -> None:
    parts = callback.data.split(":")
    deal_id = int(parts[1])
    rating_str = parts[2]

    if rating_str == "skip":
        await callback.message.edit_text("Review skipped.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    rating = int(rating_str)

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        deal = await deal_svc.get_by_id(deal_id)
        if not deal or deal.buyer_id != db_user.id:
            await callback.answer("Not authorized.", show_alert=True)
            return

        review = Review(
            deal_id=deal.id,
            reviewer_id=db_user.id,
            reviewee_id=deal.seller_id,
            rating=rating,
        )
        session.add(review)

        seller_svc = UserService(session)
        seller = await seller_svc.get_by_id(deal.seller_id)
        await seller_svc.recalculate_reputation(seller)
        await session.commit()

    stars = "⭐" * rating
    await callback.message.edit_text(
        f"Thank you! You rated this deal {stars}",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
