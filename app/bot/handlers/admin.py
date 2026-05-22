"""Admin and moderator panel."""
from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.admin_kb import admin_panel_kb, dispute_resolve_kb, user_action_kb
from app.bot.keyboards.main_menu import back_kb
from app.bot.states.dispute import AdminResolveStates
from app.config import settings
from app.database import AsyncSessionFactory
from app.models.deal import DealStatus
from app.models.dispute import Dispute, DisputeStatus, ResolutionType
from app.services.audit_service import AuditService
from app.services.deal_service import DealService
from app.services.escrow_service import EscrowService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService

router = Router()


def _is_admin_or_mod(db_user) -> bool:
    return db_user and db_user.is_moderator


@router.message(Command("admin"))
async def admin_panel(message: Message, db_user) -> None:
    if not _is_admin_or_mod(db_user):
        return
    await message.answer(
        "👑 <b>Admin Panel</b>",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:disputes")
async def list_disputes(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user):
        await callback.answer("Not authorized.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Dispute)
            .where(Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]))
            .order_by(Dispute.opened_at.asc())
            .limit(20)
        )
        disputes = result.scalars().all()

    if not disputes:
        await callback.message.edit_text(
            "✅ No open disputes.", reply_markup=back_kb("admin_panel")
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for d in disputes:
        builder.row(
            InlineKeyboardButton(
                text=f"⚖️ Deal {d.deal_id} — {d.status.value}",
                callback_data=f"admin:dispute_detail:{d.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="admin:panel"))
    await callback.message.edit_text(
        f"⚖️ <b>Open Disputes ({len(disputes)})</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:dispute_detail:"))
async def dispute_detail(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user):
        await callback.answer("Not authorized.", show_alert=True)
        return

    dispute_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        result = await session.execute(select(Dispute).where(Dispute.id == dispute_id))
        dispute = result.scalar_one_or_none()

        if not dispute:
            await callback.answer("Dispute not found.", show_alert=True)
            return

        deal_svc = DealService(session)
        deal = await deal_svc.get_by_id(dispute.deal_id)
        opener = await UserService(session).get_by_id(dispute.opened_by_id)

    evidence_count = len(dispute.evidence_file_ids or [])
    text = (
        f"⚖️ <b>Dispute #{dispute.id}</b>\n\n"
        f"Deal: <code>{deal.deal_number if deal else 'N/A'}</code>\n"
        f"Amount: {deal.amount} {deal.currency.symbol if deal else 'N/A'}\n"
        f"Opened by: {opener.display_name if opener else 'Unknown'}\n"
        f"Status: {dispute.status.value}\n"
        f"Reason: {dispute.reason}\n"
        f"Evidence: {evidence_count} file(s)\n"
        f"Opened: {dispute.opened_at.strftime('%d %b %Y %H:%M UTC')}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=dispute_resolve_kb(dispute.id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:resolve:"))
async def resolve_dispute(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not _is_admin_or_mod(db_user):
        await callback.answer("Not authorized.", show_alert=True)
        return

    parts = callback.data.split(":")
    dispute_id = int(parts[2])
    resolution_type = parts[3]

    await state.update_data(
        admin_dispute_id=dispute_id,
        admin_resolution_type=resolution_type,
    )

    if resolution_type == "partial_split":
        await state.set_state(AdminResolveStates.enter_split_percent)
        await callback.message.answer(
            "Enter the buyer's share percentage (0–100):\n"
            "e.g. 50 means 50% to buyer, 50% to seller"
        )
    else:
        await state.set_state(AdminResolveStates.enter_notes)
        await callback.message.answer("Enter resolution notes (visible to both parties):")
    await callback.answer()


@router.message(AdminResolveStates.enter_split_percent)
async def admin_split_percent(message: Message, state: FSMContext) -> None:
    try:
        pct = Decimal(message.text.strip())
        if not (0 <= pct <= 100):
            raise ValueError
    except Exception:
        await message.answer("❌ Enter a number between 0 and 100.")
        return

    await state.update_data(buyer_split=str(pct), seller_split=str(100 - pct))
    await state.set_state(AdminResolveStates.enter_notes)
    await message.answer(
        f"Buyer: {pct}%, Seller: {100 - pct}%\n\nEnter resolution notes:"
    )


@router.message(AdminResolveStates.enter_notes)
async def admin_resolution_notes(message: Message, state: FSMContext) -> None:
    await state.update_data(resolution_notes=message.text.strip())
    await state.set_state(AdminResolveStates.confirm)

    data = await state.get_data()
    resolution = data["admin_resolution_type"]
    notes = data["resolution_notes"]
    split_info = ""
    if resolution == "partial_split":
        split_info = f"\nSplit: {data['buyer_split']}% buyer / {data['seller_split']}% seller"

    await message.answer(
        f"Confirm resolution:\n"
        f"Type: <b>{resolution}</b>{split_info}\n"
        f"Notes: {notes}\n\nType YES to confirm:",
        parse_mode="HTML",
    )


@router.message(AdminResolveStates.confirm)
async def admin_confirm_resolution(message: Message, state: FSMContext, db_user) -> None:
    if message.text.strip().upper() != "YES":
        await state.clear()
        await message.answer("Resolution cancelled.")
        return

    data = await state.get_data()
    dispute_id = data["admin_dispute_id"]
    resolution_type_str = data["admin_resolution_type"]
    notes = data["resolution_notes"]

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        from datetime import datetime, timezone

        result = await session.execute(select(Dispute).where(Dispute.id == dispute_id))
        dispute = result.scalar_one_or_none()
        if not dispute:
            await message.answer("Dispute not found.")
            await state.clear()
            return

        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        notif_svc = NotificationService(session, message.bot)
        audit = AuditService(session)

        deal = await deal_svc.get_by_id(dispute.deal_id)
        buyer = await UserService(session).get_by_id(deal.buyer_id)
        seller = await UserService(session).get_by_id(deal.seller_id)

        # Apply resolution
        res_type = ResolutionType(resolution_type_str)
        dispute.resolution_type = res_type
        dispute.resolution_notes = notes
        dispute.status = DisputeStatus.RESOLVED
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.assigned_to_id = db_user.id

        if resolution_type_str == "partial_split":
            dispute.buyer_split_percent = Decimal(data["buyer_split"])
            dispute.seller_split_percent = Decimal(data["seller_split"])

        if res_type == ResolutionType.BUYER_REFUND:
            await deal_svc.refund(deal)
            # In production: call escrow_svc.refund_to_buyer(deal, buyer_address)
            buyer.total_disputes_won += 1
        elif res_type == ResolutionType.SELLER_RELEASE:
            deal.status = DealStatus.COMPLETED
            await escrow_svc.release_funds_to_seller(deal)
            seller.total_disputes_won += 1
        # partial_split and no_action: implement payout logic per chain

        resolution_label = {
            "buyer_refund": "Full refund to buyer",
            "seller_release": "Funds released to seller",
            "partial_split": f"Split: {data.get('buyer_split', 50)}% buyer / {data.get('seller_split', 50)}% seller",
            "no_action": "No action taken",
        }.get(resolution_type_str, resolution_type_str)

        await notif_svc.dispute_resolved(deal, buyer, seller, resolution_label)
        await audit.dispute_resolved(db_user.id, dispute.id, resolution_label)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Dispute #{dispute_id} resolved: {resolution_label}",
        reply_markup=admin_panel_kb(),
    )


# ── User management ──────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:ban:"))
async def ban_user(callback: CallbackQuery, db_user) -> None:
    if not db_user or not db_user.is_admin:
        await callback.answer("Admin only.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        target = await svc.get_by_id(target_id)
        if target:
            await svc.ban(target, "Admin action", db_user)
            await audit.user_banned(db_user.id, target.id, "Admin action")
            await session.commit()
    await callback.answer(f"User {target_id} banned.", show_alert=True)


@router.callback_query(F.data.startswith("admin:unban:"))
async def unban_user(callback: CallbackQuery, db_user) -> None:
    if not db_user or not db_user.is_admin:
        await callback.answer("Admin only.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        target = await svc.get_by_id(target_id)
        if target:
            await svc.unban(target)
            await session.commit()
    await callback.answer(f"User {target_id} unbanned.", show_alert=True)


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user):
        await callback.answer("Not authorized.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select, func
        from app.models.user import User
        from app.models.deal import Deal
        from app.models.transaction import Transaction

        user_count = (await session.execute(select(func.count(User.id)))).scalar_one()
        deal_count = (await session.execute(select(func.count(Deal.id)))).scalar_one()
        completed = (await session.execute(
            select(func.count(Deal.id)).where(Deal.status == DealStatus.COMPLETED)
        )).scalar_one()
        active_disputes = (await session.execute(
            select(func.count(Dispute.id)).where(
                Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW])
            )
        )).scalar_one()

    text = (
        f"📊 <b>Platform Statistics</b>\n\n"
        f"Total Users: <b>{user_count}</b>\n"
        f"Total Deals: <b>{deal_count}</b>\n"
        f"Completed Deals: <b>{completed}</b>\n"
        f"Open Disputes: <b>{active_disputes}</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_kb("admin:panel"), parse_mode="HTML")
    await callback.answer()
