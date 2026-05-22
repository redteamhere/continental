"""Payment flow — show escrow wallet address and QR code."""
from __future__ import annotations

import io

import qrcode
from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from app.bot.keyboards.deal_kb import payment_detail_kb
from app.bot.keyboards.main_menu import back_kb
from app.database import AsyncSessionFactory
from app.services.deal_service import DealService
from app.services.escrow_service import EscrowService
from app.services.user_service import UserService

router = Router()


def _make_qr(data: str) -> BufferedInputFile:
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="payment_qr.png")


@router.callback_query(F.data.startswith("deal:pay:"))
async def show_payment_details(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        deal = await deal_svc.get_by_id(deal_id)

        if not deal or deal.buyer_id != db_user.id:
            await callback.answer("Not authorized.", show_alert=True)
            return

        wallet = await escrow_svc.get_wallet_for_deal(deal)
        if not wallet:
            await callback.answer("Wallet not ready. Please try again.", show_alert=True)
            return

    currency_labels = {
        "USDT_TRC20": "USDT (TRC20 network)",
        "BTC": "Bitcoin (BTC)",
        "ETH": "Ethereum (ETH)",
        "LTC": "Litecoin (LTC)",
    }
    network_warnings = {
        "USDT_TRC20": "⚠️ Send ONLY via <b>TRC20</b> network. ETH/ERC20 will be lost.",
        "BTC": "⚠️ Bitcoin network only. Do not send to other addresses.",
        "ETH": "⚠️ Ethereum mainnet only.",
        "LTC": "⚠️ Litecoin network only.",
    }

    label = currency_labels.get(deal.currency.value, deal.currency.value)
    warning = network_warnings.get(deal.currency.value, "")

    text = (
        f"💳 <b>Fund Escrow Wallet</b>\n\n"
        f"Deal: <code>{deal.deal_number}</code>\n\n"
        f"Send exactly:\n"
        f"<code>{deal.amount}</code> <b>{label}</b>\n\n"
        f"To address:\n"
        f"<code>{wallet.address}</code>\n\n"
        f"{warning}\n\n"
        f"🔄 This bot monitors the blockchain automatically.\n"
        f"Your deal will update once payment is confirmed."
    )

    # Send QR code as photo
    qr_file = _make_qr(wallet.address)
    await callback.message.answer_photo(
        qr_file,
        caption=text,
        parse_mode="HTML",
        reply_markup=payment_detail_kb(deal.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deal:check_payment:"))
async def check_payment_status(callback: CallbackQuery, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        escrow_svc = EscrowService(session)
        deal = await deal_svc.get_by_id(deal_id)

        if not deal or db_user.id not in (deal.buyer_id, deal.seller_id):
            await callback.answer("Not found.", show_alert=True)
            return

        wallet = await escrow_svc.get_wallet_for_deal(deal)

    from app.models.deal import DealStatus
    status_text = {
        DealStatus.AWAITING_PAYMENT: "⏳ No payment detected yet.",
        DealStatus.FUNDED: f"✅ Payment confirmed! {wallet.confirmed_balance if wallet else ''} received.",
        DealStatus.IN_PROGRESS: "⚙️ Deal in progress.",
        DealStatus.COMPLETED: "✅ Deal complete.",
    }.get(deal.status, f"Status: {deal.status.value}")

    await callback.answer(status_text, show_alert=True)
