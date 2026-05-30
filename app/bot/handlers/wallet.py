"""Wallet overview — escrow balances and recent transactions."""
from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.bot.keyboards.main_menu import back_kb
from app.database import AsyncSessionFactory
from app.i18n.translations import get_lang
from app.models.deal import Deal, DealStatus
from app.models.transaction import Transaction, TxStatus
from app.models.wallet import Wallet

router = Router()


@router.callback_query(F.data == "menu:wallet")
async def show_wallet(callback: CallbackQuery, db_user) -> None:
    if not db_user:
        await callback.answer("Please /start first.", show_alert=True)
        return

    lang = get_lang(db_user)

    async with AsyncSessionFactory() as session:
        # ── Active escrow positions (deals where user is buyer) ───────────
        active_statuses = [DealStatus.FUNDED, DealStatus.IN_PROGRESS, DealStatus.AWAITING_PAYMENT]
        deals_result = await session.execute(
            select(Deal)
            .where(Deal.buyer_id == db_user.id, Deal.status.in_(active_statuses))
            .order_by(Deal.created_at.desc())
        )
        active_deals = list(deals_result.scalars().all())

        # Fetch wallets for those deals
        wallet_map: dict[int, Wallet] = {}
        if active_deals:
            deal_ids = [d.id for d in active_deals]
            wallets_result = await session.execute(
                select(Wallet).where(Wallet.deal_id.in_(deal_ids))
            )
            for w in wallets_result.scalars().all():
                wallet_map[w.deal_id] = w

        # ── Recent confirmed transactions ─────────────────────────────────
        txs_result = await session.execute(
            select(Transaction)
            .join(Deal, Transaction.deal_id == Deal.id)
            .where(
                (Deal.buyer_id == db_user.id) | (Deal.seller_id == db_user.id),
                Transaction.status == TxStatus.CONFIRMED,
            )
            .order_by(Transaction.confirmed_at.desc())
            .limit(5)
        )
        recent_txs = list(txs_result.scalars().all())

    # ── Build message ─────────────────────────────────────────────────────
    lines: list[str] = ["💰 <b>My Wallet</b>\n"]

    # Escrow positions
    if active_deals:
        lines.append("🔒 <b>Funds in Escrow:</b>")
        total = Decimal("0")
        for deal in active_deals:
            wallet = wallet_map.get(deal.id)
            balance = wallet.confirmed_balance if wallet else Decimal("0")
            total += balance
            status_icon = {
                DealStatus.AWAITING_PAYMENT: "⏳",
                DealStatus.FUNDED:           "💰",
                DealStatus.IN_PROGRESS:      "⚙️",
            }.get(deal.status, "•")
            addr = f"<code>{wallet.address[:12]}…</code>" if wallet and wallet.address else "—"
            lines.append(
                f"  {status_icon} <code>{deal.deal_number}</code> — "
                f"<b>{deal.amount} {deal.currency.symbol}</b>\n"
                f"       Wallet: {addr}"
            )
        lines.append(f"\n📊 Total locked: <b>${total:.2f}</b>")
    else:
        lines.append("🔒 <b>Funds in Escrow:</b> none")

    # Recent transactions
    lines.append("")
    if recent_txs:
        lines.append("📋 <b>Recent Transactions:</b>")
        for tx in recent_txs:
            date = tx.confirmed_at.strftime("%d %b %H:%M") if tx.confirmed_at else "—"
            lines.append(
                f"  ✅ <b>{tx.amount} {tx.currency}</b> — {date}\n"
                f"       <code>{tx.tx_hash[:20]}…</code>"
            )
    else:
        lines.append("📋 <b>Recent Transactions:</b> none")

    text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=back_kb(lang=lang),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=back_kb(lang=lang),
            parse_mode="HTML",
        )
    await callback.answer()
