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
        n = Notification(
            user_id=user.id,
            type=kwargs.get("type", "info"),
            message=text,
            deal_id=kwargs.get("deal_id"),
        )
        self._s.add(n)

        if self._bot:
            try:
                await self._bot.send_message(user.telegram_id, text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to send to {user.telegram_id}: {e}")

    # ── Admin notifications ──────────────────────────────────

    async def admin_deal_accepted(self, deal: Deal, buyer: User, seller: User) -> None:
        """Notify all configured admins when a seller accepts a deal."""
        from app.config import settings
        buyer_line = buyer.display_name + (f" (@{buyer.username})" if buyer.username else "")
        seller_line = seller.display_name + (f" (@{seller.username})" if seller.username else "")
        text = (
            f"✅ <b>Deal Accepted by Seller</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Buyer: {buyer_line}\n"
            f"Seller: {seller_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
            f"Currency: {deal.currency.value}\n\n"
            f"Status: ⏳ Awaiting buyer payment"
        )
        if not self._bot:
            return
        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to notify admin {admin_id}: {e}")

    async def admin_deal_created(self, deal: Deal, buyer: User, seller: User) -> None:
        """Notify all configured admins when a new deal is created."""
        from app.config import settings
        buyer_line = buyer.display_name + (f" (@{buyer.username})" if buyer.username else "")
        seller_line = seller.display_name + (f" (@{seller.username})" if seller.username else "")
        text = (
            f"📋 <b>New Deal Created</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Buyer: {buyer_line}\n"
            f"Seller: {seller_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
            f"Currency: {deal.currency.value}\n"
            f"Description: {deal.description}\n\n"
            f"Status: ⏳ Awaiting seller acceptance"
        )
        if not self._bot:
            return
        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to notify admin {admin_id}: {e}")

    # ── Deal lifecycle ───────────────────────────────────────

    async def deal_created(self, deal: Deal, buyer: User, seller: User) -> None:
        from app.bot.keyboards.deal_kb import seller_deal_kb
        text = (
            f"📋 <b>New Deal Request</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"From: {buyer.display_name}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
            f"Description: {deal.description}\n\n"
            f"Accept or decline below."
        )
        n = Notification(user_id=seller.id, type="deal_created", message=text)
        self._s.add(n)
        if self._bot:
            try:
                await self._bot.send_message(
                    seller.telegram_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=seller_deal_kb(deal),
                )
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to send to {seller.telegram_id}: {e}")

    async def deal_accepted(
        self, deal: Deal, buyer: User, seller: User, wallet_address: str = ""
    ) -> None:
        network_warnings = {
            "USDT_TRC20": "⚠️ Send ONLY via <b>TRC20 (TRON)</b> network.\nSending via ERC20 or BEP20 will result in loss of funds.",
            "USDT_BEP20": "⚠️ Send ONLY via <b>BEP20 (BNB Smart Chain)</b> network.\nSending via TRC20 or ERC20 will result in loss of funds.",
            "USDT_ERC20": "⚠️ Send ONLY via <b>ERC20 (Ethereum)</b> network.\nSending via TRC20 or BEP20 will result in loss of funds.",
            "BTC":        "⚠️ Send ONLY to this <b>Bitcoin (BTC)</b> address.\nDo not send any other coin to this address.",
        }
        currency_labels = {
            "USDT_TRC20": "USDT (TRC20 — TRON)",
            "USDT_BEP20": "USDT (BEP20 — BNB Smart Chain)",
            "USDT_ERC20": "USDT (ERC20 — Ethereum)",
            "BTC":        "BTC (Bitcoin)",
        }
        warning = network_warnings.get(deal.currency.value, "")
        label   = currency_labels.get(deal.currency.value, deal.currency.value)

        if wallet_address:
            text = (
                f"✅ <b>Deal Accepted!</b>\n\n"
                f"Deal: <code>{deal.deal_number}</code>\n"
                f"Seller <b>{seller.display_name}</b> accepted your deal.\n\n"
                f"💳 <b>Send exactly:</b>\n"
                f"<code>{deal.amount}</code> <b>{label}</b>\n\n"
                f"<b>To this address:</b>\n"
                f"<code>{wallet_address}</code>\n\n"
                f"📌 <b>Include your Deal ID as memo/reference:</b>\n"
                f"<code>{deal.deal_number}</code>\n\n"
                f"{warning}\n\n"
                f"After sending, the admin will verify and confirm your payment.\n"
                f"Both you and the seller will be notified once confirmed."
            )
        else:
            text = (
                f"✅ <b>Deal Accepted!</b>\n\n"
                f"Deal: <code>{deal.deal_number}</code>\n"
                f"Seller {seller.display_name} accepted your deal.\n\n"
                f"Please contact the admin to receive payment instructions."
            )

        n = Notification(user_id=buyer.id, type="deal_accepted", message=text)
        self._s.add(n)
        if self._bot:
            try:
                await self._bot.send_message(buyer.telegram_id, text, parse_mode="HTML")
                # Send QR code with the "I Have Paid" action button attached
                if wallet_address:
                    import io
                    import qrcode
                    from aiogram.types import BufferedInputFile
                    from app.bot.keyboards.deal_kb import payment_detail_kb
                    qr = qrcode.QRCode(version=1, box_size=8, border=4)
                    qr.add_data(wallet_address)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    qr_file = BufferedInputFile(buf.read(), filename="payment_qr.png")
                    await self._bot.send_photo(
                        buyer.telegram_id,
                        qr_file,
                        caption=f"📷 QR code for <code>{wallet_address}</code>",
                        parse_mode="HTML",
                        reply_markup=payment_detail_kb(deal.id),
                    )
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to send to {buyer.telegram_id}: {e}")

    async def buyer_payment_claimed(self, deal: Deal, buyer: User, seller: User) -> None:
        """Buyer pressed 'I Have Paid' — notify seller and all admins to verify."""
        from app.config import settings
        buyer_line  = buyer.display_name  + (f" (@{buyer.username})"  if buyer.username  else "")
        seller_line = seller.display_name + (f" (@{seller.username})" if seller.username else "")

        # ── Notify seller ──────────────────────────────────────────────
        await self._send(
            seller,
            f"💳 <b>Buyer Claims Payment Sent</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Buyer {buyer_line} says they have sent:\n"
            f"<b>{deal.amount} {deal.currency.symbol}</b>\n\n"
            f"Waiting for the admin to verify the transaction on-chain.\n"
            f"You will be notified once payment is confirmed.",
            type="payment_claimed",
            deal_id=deal.id,
        )

        # ── Notify admins ──────────────────────────────────────────────
        if not self._bot:
            return
        from app.services.escrow_service import _cold_wallet_address
        wallet_addr = _cold_wallet_address(deal.currency) or "(HD wallet)"
        admin_text = (
            f"💰 <b>Buyer Claims Payment Sent — Action Required</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Buyer: {buyer_line}\n"
            f"Seller: {seller_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n"
            f"Network: {deal.currency.chain}\n"
            f"Wallet: <code>{wallet_addr}</code>\n\n"
            f"Please verify the transaction on-chain, then confirm with:\n"
            f"<code>/confirm_payment {deal.deal_number}</code>"
        )
        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to reach admin {admin_id}: {e}")

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
        from app.bot.keyboards.deal_kb import deal_action_kb

        await self._send(
            seller,
            f"💵 <b>Funds Confirmed in Escrow!</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Amount: {deal.amount} {deal.currency.symbol} is now locked.\n"
            f"Please fulfil your part of the deal.\n\n"
            f"Use the buttons below to manage this deal:",
            type="funds_confirmed",
            deal_id=deal.id,
        )
        await self._send(
            buyer,
            f"🔒 <b>Escrow Funded</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"Your {deal.amount} {deal.currency.symbol} is safely locked.\n"
            f"Release funds once you're satisfied.\n\n"
            f"Use the buttons below to manage this deal:",
            type="funds_confirmed",
            deal_id=deal.id,
        )
        # Send action keyboards so both parties can act immediately
        if self._bot:
            for user, uid in ((seller, seller.id), (buyer, buyer.id)):
                try:
                    await self._bot.send_message(
                        user.telegram_id,
                        f"📋 <b>Deal Actions — {deal.deal_number}</b>",
                        reply_markup=deal_action_kb(deal, uid),
                        parse_mode="HTML",
                    )
                except TelegramAPIError as e:
                    logger.warning(f"[Notify] Could not send action kb to {user.telegram_id}: {e}")

    async def seller_delivered(self, deal: Deal, buyer: User, seller: User) -> None:
        from app.bot.keyboards.deal_kb import deal_action_kb

        await self._send(
            buyer,
            f"📦 <b>Seller Marked as Delivered!</b>\n\n"
            f"Deal: <code>{deal.deal_number}</code>\n"
            f"{seller.display_name} says the work is done.\n\n"
            f"✅ Release funds if satisfied.\n"
            f"⚖️ Open a dispute if there's a problem.\n"
            f"❌ Cancel if you need to.",
            type="seller_delivered",
        )
        # Send buyer their action buttons immediately
        if self._bot:
            try:
                await self._bot.send_message(
                    buyer.telegram_id,
                    f"📋 <b>Deal Actions — {deal.deal_number}</b>",
                    reply_markup=deal_action_kb(deal, buyer.id),
                    parse_mode="HTML",
                )
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Could not send action kb to {buyer.telegram_id}: {e}")

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

    # ── Admin action notifications ────────────────────────────

    async def _notify_admins(self, text: str) -> None:
        """Send a message to every configured admin. Never raises."""
        from app.config import settings
        if not self._bot:
            return
        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, text, parse_mode="HTML")
            except TelegramAPIError as e:
                logger.warning(f"[Notify] Failed to reach admin {admin_id}: {e}")

    async def admin_deal_completed(self, deal: Deal, buyer: User, seller: User) -> None:
        buyer_line = buyer.display_name + (f" (@{buyer.username})" if buyer.username else "")
        seller_line = seller.display_name + (f" (@{seller.username})" if seller.username else "")
        await self._notify_admins(
            f"🎉 <b>Deal Completed</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Buyer: {buyer_line}\n"
            f"Seller: {seller_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n\n"
            f"Buyer has released funds to the seller."
        )

    async def admin_deal_cancelled(self, deal: Deal, cancelled_by: User) -> None:
        await self._notify_admins(
            f"❌ <b>Deal Cancelled</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Cancelled by: {cancelled_by.display_name}"
            + (f" (@{cancelled_by.username})" if cancelled_by.username else "") + "\n"
            f"Reason: {deal.cancellation_reason or 'No reason provided'}"
        )

    async def admin_seller_delivered(self, deal: Deal, seller: User, buyer: User) -> None:
        seller_line = seller.display_name + (f" (@{seller.username})" if seller.username else "")
        buyer_line = buyer.display_name + (f" (@{buyer.username})" if buyer.username else "")
        await self._notify_admins(
            f"📦 <b>Seller Marked as Delivered</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Seller: {seller_line}\n"
            f"Buyer: {buyer_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n\n"
            f"Waiting for buyer to release funds."
        )

    async def admin_dispute_opened(self, deal: Deal, opened_by: User, reason: str) -> None:
        opener_line = opened_by.display_name + (f" (@{opened_by.username})" if opened_by.username else "")
        await self._notify_admins(
            f"⚖️ <b>Dispute Opened</b>\n\n"
            f"Deal ID: <code>{deal.deal_number}</code>\n"
            f"Opened by: {opener_line}\n"
            f"Amount: <b>{deal.amount} {deal.currency.symbol}</b>\n\n"
            f"<b>Reason:</b>\n{reason}\n\n"
            f"Use /admin → Disputes to review."
        )
