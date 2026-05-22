"""Send Telegram notifications to users via the bot."""
from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import Notification
from app.models.deal import Deal
from app.models.user import User


class NotificationService:
    def __init__(self, session: AsyncSession, bot: Optional[Bot] = None) -> None:
        self._s = session
        self._bot = bot

    async def _send(self, user: User, text: str, **kwargs) -> None:
        """Send message and persist notification record."""
        n = Notification(user_id=user.id, type=kwargs.get("type", "info"), message=text)
        self._s.add(n)

        if self._bot:
            try:
                await self._bot.send_message(user.telegram_id, text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to send to {user.telegram_id}: {e}")

    # ── Deal lifecycle ───────────────────────────────────────

    async def deal_created(self, deal: Deal, buyer: User, seller: User) -> None:
        await self._send(
            seller,
            f"📋 <b>New Deal Request</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"From: {buyer.display_name}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
            f"Description: {deal.description}\n\n"
            f"Use /deal_{deal.deal_number} to accept or decline.",
            type="deal_created",
        )

    async def deal_accepted(self, deal: Deal, buyer: User, seller: User) -> None:
        await self._send(
            buyer,
            f"✅ <b>Deal Accepted!</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Seller {seller.display_name} accepted your deal.\n\n"
            f"Please fund the escrow wallet to proceed.",
            type="deal_accepted",
        )

    async def payment_detected(self, deal: Deal, buyer: User, seller: User, amount) -> None:
        for user in (buyer, seller):
            await self._send(
                user,
                f"💰 <b>Payment Detected</b>\n\n"
                f"Deal: <code>{deal.deal_number}</code>\n"
                f"Amount: {amount} {deal.currency.symbol}\n"
                f"Status: Awaiting confirmations…",
                type="payment_detected",
            )

    async def payment_confirmed(self, deal: Deal, buyer: User, seller: User) -> None:
        await self._send(
            seller,
            f"💵 <b>Funds Confirmed in Escrow!</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Amount: {deal.amount} {deal.currency.symbol} is now locked.\n"
            f"Please fulfil your part of the deal.",
            type="funds_confirmed",
        )
        await self._send(
            buyer,
            f"🔒 <b>Escrow Funded</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Your {deal.amount} {deal.currency.symbol} is safely locked.\n"
            f"Release funds once you're satisfied.",
            type="funds_confirmed",
        )

    async def seller_delivered(self, deal: Deal, buyer: User, seller: User) -> None:
        await self._send(
            buyer,
            f"📦 <b>Seller Marked as Delivered!</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"{seller.display_name} says the work is done.\n\n"
            f"✅ If you're satisfied — open the deal and tap <b>Release Funds</b>.\n"
            f"⚖️ If there's a problem — tap <b>Open Dispute</b>.",
            type="seller_delivered",
        )

    async def deal_completed(self, deal: Deal, buyer: User, seller: User) -> None:
        await self._send(
            seller,
            f"🎉 <b>Funds Released!</b>\n\n"
            f"Deal <code>{deal.deal_number}</code> is complete.\n"
            f"You will receive {deal.net_amount} {deal.currency.symbol} shortly.",
            type="deal_completed",
        )
        await self._send(
            buyer,
            f"✅ <b>Deal Complete</b>\n\n"
            f"Deal <code>{deal.deal_number}</code> closed.\n"
            f"Please leave a review for {seller.display_name}.",
            type="deal_completed",
        )

    async def deal_cancelled(self, deal: Deal, buyer: User, seller: User) -> None:
        for user in (buyer, seller):
            await self._send(
                user,
                f"❌ <b>Deal Cancelled</b>\n\n"
                f"Deal <code>{deal.deal_number}</code> has been cancelled.\n"
                f"Reason: {deal.cancellation_reason}",
                type="deal_cancelled",
            )

    async def dispute_opened(self, deal: Deal, opened_by: User, other_party: User) -> None:
        await self._send(
            other_party,
            f"⚖️ <b>Dispute Opened</b>\n\n"
            f"Deal <code>{deal.deal_number}</code>: {opened_by.display_name} opened a dispute.\n"
            f"A moderator will review the case.",
            type="dispute_opened",
        )

    async def dispute_resolved(
        self, deal: Deal, buyer: User, seller: User, resolution: str
    ) -> None:
        for user in (buyer, seller):
            await self._send(
                user,
                f"⚖️ <b>Dispute Resolved</b>\n\n"
                f"Deal <code>{deal.deal_number}</code>\n"
                f"Resolution: {resolution}",
                type="dispute_resolved",
            )

    async def chat_message(self, recipient: User, sender_role: str, deal_number: str, text: str) -> None:
        await self._send(
            recipient,
            f"💬 <b>{sender_role} [{deal_number}]:</b>\n{text}",
            type="chat_message",
        )

    async def deadline_warning(self, deal: Deal, buyer: User, seller: User) -> None:
        for user in (buyer, seller):
            await self._send(
                user,
                f"⏰ <b>Deal Expiring Soon</b>\n\n"
                f"Deal <code>{deal.deal_number}</code> expires in 24 hours.\n"
                f"Please complete or contact the other party.",
                type="deadline_warning",
            )
