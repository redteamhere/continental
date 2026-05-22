"""Create private Telegram supergroups for deal chats using Telethon (MTProto)."""
from __future__ import annotations

from loguru import logger

from app.config import settings


async def create_deal_group(deal_number: str) -> tuple[int, str]:
    """
    Create a private Telegram supergroup for a deal via Telethon MTProto.
    Returns (group_id, invite_link).

    Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env
    (from https://my.telegram.org/apps).
    """
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.channels import CreateChannelRequest
        from telethon.tl.functions.messages import ExportChatInviteRequest
    except ImportError:
        raise RuntimeError(
            "telethon is not installed. Run: pip install telethon"
        )

    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env — "
            "get them at https://my.telegram.org/apps"
        )

    client = TelegramClient(
        StringSession(),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
        system_version="4.16.30-vxCUSTOM",
    )

    await client.start(bot_token=settings.BOT_TOKEN)
    try:
        result = await client(CreateChannelRequest(
            title=f"🔒 Deal {deal_number}",
            about=(
                f"Private escrow deal chat for {deal_number}.\n"
                "Managed by EscrowBot — do not share this link with third parties."
            ),
            megagroup=True,
        ))
        group = result.chats[0]

        invite_result = await client(ExportChatInviteRequest(peer=group))
        return group.id, invite_result.link
    finally:
        await client.disconnect()


async def create_and_notify_group(deal_id: int, bot) -> None:
    """
    Background task: create a Telegram supergroup for the deal, persist the
    invite link, and notify both buyer and seller.
    """
    from app.database import AsyncSessionFactory
    from app.services.deal_service import DealService
    from app.services.user_service import UserService
    from aiogram.exceptions import TelegramAPIError

    try:
        # Load deal + parties (read only, then close session)
        async with AsyncSessionFactory() as session:
            deal = await DealService(session).get_by_id(deal_id)
            if not deal:
                logger.warning(f"[GroupService] Deal {deal_id} not found.")
                return
            if deal.chat_invite_link:
                logger.info(f"[GroupService] Group already exists for deal {deal_id}.")
                return

            deal_number = deal.deal_number
            buyer = await UserService(session).get_by_id(deal.buyer_id)
            seller = await UserService(session).get_by_id(deal.seller_id)
            buyer_tg_id = buyer.telegram_id if buyer else None
            seller_tg_id = seller.telegram_id if seller else None

        # Create the group (outside DB session — may take a few seconds)
        group_id, invite_link = await create_deal_group(deal_number)
        logger.info(f"[GroupService] Group created for deal {deal_number}: {invite_link}")

        # Persist invite link
        async with AsyncSessionFactory() as session:
            deal = await DealService(session).get_by_id(deal_id)
            if deal:
                deal.chat_group_id = group_id
                deal.chat_invite_link = invite_link
                await session.commit()

        # Notify both parties
        text = (
            f"💬 <b>Private Deal Chat Ready!</b>\n\n"
            f"Deal: <code>{deal_number}</code>\n\n"
            f"A private group has been created for you and your counterpart to "
            f"communicate, share files, and coordinate.\n\n"
            f"👉 <a href='{invite_link}'>Join the deal chat</a>"
        )
        for tg_id in (buyer_tg_id, seller_tg_id):
            if tg_id:
                try:
                    await bot.send_message(
                        tg_id, text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except TelegramAPIError as e:
                    logger.warning(f"[GroupService] Could not notify {tg_id}: {e}")

    except Exception as e:
        logger.error(f"[GroupService] Failed to create group for deal {deal_id}: {e}")
