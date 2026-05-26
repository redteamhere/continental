"""Admin and moderator panel."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.bot.keyboards.admin_kb import admin_panel_kb, dispute_resolve_kb, user_action_kb
from app.bot.keyboards.main_menu import back_kb
from app.bot.states.dispute import AdminResolveStates
from app.config import settings
from app.database import AsyncSessionFactory
from app.models.deal import Deal, DealStatus
from app.models.dispute import Dispute, DisputeStatus, ResolutionType
from app.models.transaction import Transaction
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.services.audit_service import AuditService
from app.services.deal_service import DealService
from app.services.escrow_service import EscrowService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService

router = Router()

# Keep strong references to background tasks so they aren't garbage-collected
_background_tasks: set = set()

_USERS_PER_PAGE = 10


# ── Admin lookup FSM states ───────────────────────────────────
class AdminLookupStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_deal_number = State()


def _is_admin_or_mod(db_user, tg_id: int = 0) -> bool:
    from app.config import settings
    return bool(
        (db_user and db_user.is_moderator)
        or tg_id in settings.ADMIN_IDS
    )


@router.message(Command("admin"))
async def admin_panel(message: Message, db_user) -> None:
    if not _is_admin_or_mod(db_user, message.from_user.id):
        return
    await message.answer(
        "👑 <b>Admin Panel</b>",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:panel")
async def admin_panel_cb(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    """Back button target for all admin sub-pages."""
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 <b>Admin Panel</b>",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:disputes")
async def list_disputes(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
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
            "✅ No open disputes.", reply_markup=back_kb("admin:panel")
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
    if not _is_admin_or_mod(db_user, callback.from_user.id):
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
    if not _is_admin_or_mod(db_user, callback.from_user.id):
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

        await notif_svc.dispute_resolved(deal, buyer, seller, resolution_label, notes=notes)
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
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        audit = AuditService(session)
        target = await svc.get_by_id(target_id)
        if not target:
            await callback.answer("User not found.", show_alert=True)
            return
        if target.telegram_id in settings.ADMIN_IDS:
            await callback.answer("Cannot ban an admin.", show_alert=True)
            return
        await svc.ban(target, "Admin action", db_user)
        await audit.user_banned(db_user.id, target.id, "Admin action")
        await session.commit()
    await callback.answer(f"✅ User {target_id} banned.", show_alert=True)
    # Refresh user detail view
    await _show_user_detail(callback, target_id)


@router.callback_query(F.data.startswith("admin:unban:"))
async def unban_user(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        target = await svc.get_by_id(target_id)
        if not target:
            await callback.answer("User not found.", show_alert=True)
            return
        await svc.unban(target)
        await session.commit()
    await callback.answer(f"✅ User {target_id} unbanned.", show_alert=True)
    await _show_user_detail(callback, target_id)


# ── Users list ───────────────────────────────────────────────

@router.callback_query(F.data == "admin:users")
async def list_users(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    await _show_users_page(callback, page=0)


@router.callback_query(F.data.startswith("admin:users:page:"))
async def users_page(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    page = int(callback.data.split(":")[3])
    await _show_users_page(callback, page=page)


async def _show_users_page(callback: CallbackQuery, page: int) -> None:
    offset = page * _USERS_PER_PAGE
    async with AsyncSessionFactory() as session:
        total = (await session.execute(select(func.count(User.id)))).scalar_one()
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(_USERS_PER_PAGE)
        )
        users = result.scalars().all()

    builder = InlineKeyboardBuilder()
    for u in users:
        status_icon = "🚫" if u.is_banned else ("👑" if u.role == UserRole.ADMIN else ("🛡️" if u.role == UserRole.MODERATOR else "👤"))
        name = f"@{u.username}" if u.username else u.first_name
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {name} — ID {u.id}",
                callback_data=f"admin:user_detail:{u.id}",
            )
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:users:page:{page - 1}"))
    if offset + _USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"admin:users:page:{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="admin:panel"))

    await callback.message.edit_text(
        f"👥 <b>Users</b> ({total} total) — page {page + 1}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── User detail ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:user_detail:"))
async def user_detail(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    await _show_user_detail(callback, target_id)


async def _show_user_detail(callback: CallbackQuery, target_id: int) -> None:
    async with AsyncSessionFactory() as session:
        target = await UserService(session).get_by_id(target_id)
        if not target:
            await callback.answer("User not found.", show_alert=True)
            return
        deal_count = (await session.execute(
            select(func.count(Deal.id)).where(
                (Deal.buyer_id == target.id) | (Deal.seller_id == target.id)
            )
        )).scalar_one()

    status_parts = []
    if target.is_banned:
        status_parts.append(f"🚫 <b>BANNED</b> — {target.ban_reason or 'no reason'}")
    if target.role == UserRole.ADMIN:
        status_parts.append("👑 Admin")
    elif target.role == UserRole.MODERATOR:
        status_parts.append("🛡️ Moderator")
    else:
        status_parts.append("👤 User")

    name = f"{target.first_name} {target.last_name or ''}".strip()
    username = f"@{target.username}" if target.username else "—"

    text = (
        f"👤 <b>User #{target.id}</b>\n\n"
        f"Name: {name}\n"
        f"Username: {username}\n"
        f"Telegram ID: <code>{target.telegram_id}</code>\n"
        f"Status: {' | '.join(status_parts)}\n"
        f"Joined: {target.created_at.strftime('%d %b %Y')}\n\n"
        f"Deals: <b>{deal_count}</b>\n"
        f"Reputation: <b>{target.reputation_score:.1f}</b>/5.0\n"
        f"Referral Code: <code>{target.referral_code}</code>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=user_action_kb(target.id, target.is_banned),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Set / unset moderator ────────────────────────────────────

@router.callback_query(F.data.startswith("admin:set_mod:"))
async def set_moderator(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])
    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        target = await svc.get_by_id(target_id)
        if not target:
            await callback.answer("User not found.", show_alert=True)
            return
        if target.telegram_id in settings.ADMIN_IDS:
            await callback.answer("Cannot change admin's role.", show_alert=True)
            return
        # Toggle: if already moderator → back to user; if user → promote to moderator
        if target.role == UserRole.MODERATOR:
            await svc.set_role(target, UserRole.USER)
            msg = f"✅ @{target.username or target.first_name} is now a regular User."
        else:
            await svc.set_role(target, UserRole.MODERATOR)
            msg = f"✅ @{target.username or target.first_name} is now a Moderator."
        await session.commit()
    await callback.answer(msg, show_alert=True)
    await _show_user_detail(callback, target_id)


# ── User deals ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:user_deals:"))
async def user_deals(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        target = await UserService(session).get_by_id(target_id)
        if not target:
            await callback.answer("User not found.", show_alert=True)
            return
        result = await session.execute(
            select(Deal)
            .where((Deal.buyer_id == target_id) | (Deal.seller_id == target_id))
            .order_by(Deal.created_at.desc())
            .limit(20)
        )
        deals = result.scalars().all()

    if not deals:
        await callback.message.edit_text(
            f"📋 No deals found for user #{target_id}.",
            reply_markup=back_kb(f"admin:user_detail:{target_id}"),
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    status_icons = {
        "pending": "🟡", "awaiting_payment": "💳", "funded": "💰",
        "in_progress": "⚙️", "completed": "✅", "cancelled": "❌",
        "disputed": "⚖️", "refunded": "↩️",
    }
    for d in deals:
        icon = status_icons.get(d.status.value, "❓")
        role = "B" if d.buyer_id == target_id else "S"
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} [{role}] {d.deal_number} — {d.amount} {d.currency.symbol}",
                callback_data=f"deal:view:{d.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data=f"admin:user_detail:{target_id}"))

    name = f"@{target.username}" if target.username else target.first_name
    await callback.message.edit_text(
        f"📋 <b>Deals for {name}</b> (last {len(deals)})",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Transactions list ────────────────────────────────────────

@router.callback_query(F.data == "admin:transactions")
async def list_transactions(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Transaction).order_by(Transaction.detected_at.desc()).limit(20)
        )
        txs = result.scalars().all()

    if not txs:
        await callback.message.edit_text(
            "💰 No transactions recorded yet.",
            reply_markup=back_kb("admin:panel"),
        )
        await callback.answer()
        return

    lines = []
    status_icons = {"pending": "🟡", "confirming": "🔄", "confirmed": "✅", "failed": "❌", "duplicate": "🔁"}
    for tx in txs:
        icon = status_icons.get(tx.status.value, "❓")
        date = tx.detected_at.strftime("%d %b %H:%M")
        lines.append(
            f"{icon} <code>{tx.tx_hash[:12]}…</code> | {tx.amount} {tx.currency} | {date}"
        )

    text = "💰 <b>Recent Transactions</b> (last 20)\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_kb("admin:panel"), parse_mode="HTML")
    await callback.answer()


# ── Lookup user ──────────────────────────────────────────────

@router.callback_query(F.data == "admin:lookup_user")
async def lookup_user_prompt(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    await state.set_state(AdminLookupStates.waiting_for_username)
    await callback.message.edit_text(
        "🔍 <b>Lookup User</b>\n\nSend the user's <b>@username</b> or <b>Telegram ID</b>:",
        reply_markup=back_kb("admin:panel"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminLookupStates.waiting_for_username)
async def lookup_user_result(message: Message, state: FSMContext, db_user) -> None:
    if not _is_admin_or_mod(db_user, message.from_user.id):
        return
    query = message.text.strip()
    await state.clear()

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        if query.lstrip("@").isdigit():
            # Try Telegram ID first, then DB ID
            tg_id = int(query.lstrip("@"))
            target = await svc.get_by_telegram_id(tg_id) or await svc.get_by_id(tg_id)
        else:
            target = await svc.get_by_username(query.lstrip("@"))

        if not target:
            await message.answer(
                f"❌ User <code>{query}</code> not found.",
                reply_markup=back_kb("admin:panel"),
                parse_mode="HTML",
            )
            return

        deal_count = (await session.execute(
            select(func.count(Deal.id)).where(
                (Deal.buyer_id == target.id) | (Deal.seller_id == target.id)
            )
        )).scalar_one()

        status_parts = []
        if target.is_banned:
            status_parts.append(f"🚫 BANNED — {target.ban_reason or 'no reason'}")
        if target.role == UserRole.ADMIN:
            status_parts.append("👑 Admin")
        elif target.role == UserRole.MODERATOR:
            status_parts.append("🛡️ Moderator")
        else:
            status_parts.append("👤 User")

        name = f"{target.first_name} {target.last_name or ''}".strip()
        username = f"@{target.username}" if target.username else "—"
        text = (
            f"👤 <b>User #{target.id}</b>\n\n"
            f"Name: {name}\n"
            f"Username: {username}\n"
            f"Telegram ID: <code>{target.telegram_id}</code>\n"
            f"Status: {' | '.join(status_parts)}\n"
            f"Joined: {target.created_at.strftime('%d %b %Y')}\n\n"
            f"Deals: <b>{deal_count}</b>\n"
            f"Reputation: <b>{target.reputation_score:.1f}</b>/5.0\n"
            f"Referral Code: <code>{target.referral_code}</code>"
        )
        await message.answer(
            text,
            reply_markup=user_action_kb(target.id, target.is_banned),
            parse_mode="HTML",
        )


# ── Lookup deal ──────────────────────────────────────────────

@router.callback_query(F.data == "admin:lookup_deal")
async def lookup_deal_prompt(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    await state.set_state(AdminLookupStates.waiting_for_deal_number)
    await callback.message.edit_text(
        "🔍 <b>Lookup Deal</b>\n\nSend the deal number (e.g. <code>ESC-A1B2C3</code>):",
        reply_markup=back_kb("admin:panel"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminLookupStates.waiting_for_deal_number)
async def lookup_deal_result(message: Message, state: FSMContext, db_user) -> None:
    if not _is_admin_or_mod(db_user, message.from_user.id):
        return
    deal_number = message.text.strip().upper()
    await state.clear()

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(Deal.deal_number == deal_number)
        )
        deal = result.scalar_one_or_none()
        if not deal:
            await message.answer(
                f"❌ Deal <code>{deal_number}</code> not found.",
                reply_markup=back_kb("admin:panel"),
                parse_mode="HTML",
            )
            return

        svc = UserService(session)
        buyer = await svc.get_by_id(deal.buyer_id)
        seller = await svc.get_by_id(deal.seller_id)

        buyer_name = f"@{buyer.username}" if buyer and buyer.username else (buyer.first_name if buyer else "Unknown")
        seller_name = f"@{seller.username}" if seller and seller.username else (seller.first_name if seller else "Unknown")
        created = deal.created_at.strftime("%d %b %Y %H:%M UTC")
        funded = deal.funded_at.strftime("%d %b %Y %H:%M UTC") if deal.funded_at else "—"

        text = (
            f"📋 <b>Deal {deal.deal_number}</b>\n\n"
            f"Status: <b>{deal.status.value}</b>\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n\n"
            f"Buyer: {buyer_name}\n"
            f"Seller: {seller_name}\n"
            f"Description: {deal.description or '—'}\n\n"
            f"Created: {created}\n"
            f"Funded: {funded}"
        )

        builder = InlineKeyboardBuilder()
        if deal.status == DealStatus.AWAITING_PAYMENT:
            builder.row(InlineKeyboardButton(
                text="✅ Confirm Payment",
                callback_data=f"admin:confirm_deal:{deal.id}",
            ))
        builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="admin:panel"))

        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ── Quick confirm payment from deal lookup ────────────────────

@router.callback_query(F.data.startswith("admin:confirm_deal:"))
async def confirm_deal_cb(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Deal).where(Deal.id == deal_id))
        deal = result.scalar_one_or_none()
        if not deal or deal.status != DealStatus.AWAITING_PAYMENT:
            await callback.answer("Deal not found or wrong status.", show_alert=True)
            return

        deal.status = DealStatus.FUNDED
        deal.funded_at = datetime.now(timezone.utc)

        if deal.escrow_wallet_id:
            wallet_result = await session.execute(
                select(Wallet).where(Wallet.id == deal.escrow_wallet_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet:
                wallet.confirmed_balance = deal.amount

        svc = UserService(session)
        buyer = await svc.get_by_id(deal.buyer_id)
        seller = await svc.get_by_id(deal.seller_id)

        notif = NotificationService(session, callback.bot)
        await notif.payment_confirmed(deal, buyer, seller)
        await session.commit()
        funded_deal_id = deal.id
        deal_number = deal.deal_number

    import asyncio
    from app.services.group_service import create_and_notify_group
    _task = asyncio.create_task(
        create_and_notify_group(funded_deal_id, callback.bot, admin_tg_id=callback.from_user.id)
    )
    _background_tasks.add(_task)
    _task.add_done_callback(_background_tasks.discard)

    await callback.message.edit_text(
        f"✅ <b>Payment confirmed</b>\n\n"
        f"Deal <code>{deal_number}</code> is now <b>FUNDED</b>.\n"
        f"Buyer and seller have been notified.\n"
        f"A private deal group is being created…",
        reply_markup=back_kb("admin:panel"),
        parse_mode="HTML",
    )
    await callback.answer("Payment confirmed!", show_alert=True)


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, db_user) -> None:
    if not _is_admin_or_mod(db_user, callback.from_user.id):
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


# ── Admin: confirm payment received ──────────────────────────

@router.message(Command("confirm_payment"))
async def confirm_payment(message: Message, db_user) -> None:
    """Admin: /confirm_payment DEAL-XXXXX  — mark deal as funded after verifying receipt."""
    if not _is_admin_or_mod(db_user, message.from_user.id):
        await message.answer("⛔ Admin only.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/confirm_payment DEAL-XXXXXX</code>\n"
            "Example: <code>/confirm_payment ESC-5F0DCD</code>",
            parse_mode="HTML",
        )
        return

    deal_number = parts[1].strip().upper()

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(Deal.deal_number == deal_number)
        )
        deal = result.scalar_one_or_none()

        if not deal:
            await message.answer(f"❌ Deal <code>{deal_number}</code> not found.", parse_mode="HTML")
            return

        if deal.status != DealStatus.AWAITING_PAYMENT:
            await message.answer(
                f"❌ Deal is in <b>{deal.status.value}</b> status — "
                f"can only confirm payment for <b>awaiting_payment</b> deals.",
                parse_mode="HTML",
            )
            return

        deal.status = DealStatus.FUNDED
        deal.funded_at = datetime.now(timezone.utc)

        if deal.escrow_wallet_id:
            wallet_result = await session.execute(
                select(Wallet).where(Wallet.id == deal.escrow_wallet_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet:
                wallet.confirmed_balance = deal.amount

        svc = UserService(session)
        buyer = await svc.get_by_id(deal.buyer_id)
        seller = await svc.get_by_id(deal.seller_id)

        notif = NotificationService(session, message.bot)
        await notif.payment_confirmed(deal, buyer, seller)
        # Note: deal stays FUNDED — the seller still needs to deliver.
        # Duplicate notification is prevented by blockchain_monitor checking
        # the Notification table for an existing funds_confirmed record.

        await session.commit()
        funded_deal_id = deal.id

    import asyncio
    from app.services.group_service import create_and_notify_group
    _task = asyncio.create_task(
        create_and_notify_group(funded_deal_id, message.bot, admin_tg_id=message.from_user.id)
    )
    _background_tasks.add(_task)
    _task.add_done_callback(_background_tasks.discard)

    await message.answer(
        f"✅ <b>Payment confirmed</b>\n\n"
        f"Deal <code>{deal_number}</code> is now <b>FUNDED</b>.\n"
        f"Buyer and seller have been notified.\n"
        f"Creating a private deal group…",
        parse_mode="HTML",
    )


# ── LOCAL_DEV: simulate payment ───────────────────────────────

@router.message(Command("sim_pay"))
async def sim_pay(message: Message) -> None:
    """Admin-only: instantly mark a deal as FUNDED (LOCAL_DEV mode only)."""
    if not settings.LOCAL_DEV:
        await message.answer("❌ /sim_pay is only available in LOCAL_DEV mode.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/sim_pay DEAL-XXXXXX</code>\n"
            "Example: <code>/sim_pay DEAL-A1B2C3</code>",
            parse_mode="HTML",
        )
        return

    deal_number = parts[1].strip().upper()

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(Deal.deal_number == deal_number)
        )
        deal = result.scalar_one_or_none()

        if not deal:
            await message.answer(f"❌ Deal <code>{deal_number}</code> not found.", parse_mode="HTML")
            return

        if deal.status != DealStatus.AWAITING_PAYMENT:
            await message.answer(
                f"❌ Deal is in <b>{deal.status.value}</b> status — can only simulate payment for <b>awaiting_payment</b> deals.",
                parse_mode="HTML",
            )
            return

        # Mark deal as funded
        deal.status = DealStatus.FUNDED
        deal.funded_at = datetime.now(timezone.utc)

        # Update wallet balance so the rest of the flow works
        if deal.escrow_wallet_id:
            wallet_result = await session.execute(
                select(Wallet).where(Wallet.id == deal.escrow_wallet_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet:
                wallet.confirmed_balance = deal.amount

        # Notify both parties
        svc = UserService(session)
        buyer = await svc.get_by_id(deal.buyer_id)
        seller = await svc.get_by_id(deal.seller_id)

        notif = NotificationService(session, message.bot)
        await notif.payment_confirmed(deal, buyer, seller)

        await session.commit()
        funded_deal_id = deal.id

    # Spin up private group for buyer + seller (runs in background)
    import asyncio
    from app.services.group_service import create_and_notify_group
    asyncio.create_task(create_and_notify_group(funded_deal_id, message.bot))

    await message.answer(
        f"✅ <b>[LOCAL_DEV] Payment simulated</b>\n\n"
        f"Deal <code>{deal_number}</code> is now <b>FUNDED</b>.\n"
        f"Both parties have been notified and a private group is being created.",
        parse_mode="HTML",
    )
