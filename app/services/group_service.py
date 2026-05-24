"""Create private Telegram supergroups for deal chats using Telethon (MTProto)."""
from __future__ import annotations

from loguru import logger

from app.config import settings


async def create_deal_group(deal_number: str) -> tuple[int, str]:
    """
    Create a private Telegram supergroup for a deal via Telethon MTProto.
    Returns (group_id, invite_link).

    Requirements (all must be set in Railway Variables):
      TELEGRAM_API_ID       — from https://my.telegram.org/apps
      TELEGRAM_API_HASH     — from https://my.telegram.org/apps
      TELEGRAM_SESSION_STRING — generated from a real user account (NOT a bot)
    """
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are not set. "
            "Get them at https://my.telegram.org/apps and add to Railway Variables."
        )

    if not settings.TELEGRAM_SESSION_STRING:
        raise RuntimeError(
            "TELEGRAM_SESSION_STRING is not set. "
            "Telegram bots cannot create groups — a real user session is required. "
            "See bot instructions for how to generate it."
        )

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.channels import CreateChannelRequest
        from telethon.tl.functions.messages import ExportChatInviteRequest
    except ImportError:
        raise RuntimeError("telethon is not installed. Run: pip install telethon")

    client = TelegramClient(
        StringSession(settings.TELEGRAM_SESSION_STRING),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
        system_version="4.16.30-vxCUSTOM",
    )

    await client.connect()

    try:
        # Verify the session is actually authenticated
        me = await client.get_me()
        if me is None:
            raise RuntimeError(
                "TELEGRAM_SESSION_STRING is invalid or expired. "
                "Please regenerate it and update Railway Variables."
            )
        logger.info(f"[GroupService] Telethon connected as: {me.first_name} (id={me.id})")

        # Create the private supergroup
        result = await client(CreateChannelRequest(
            title=f"🔒 Deal {deal_number}",
            about=(
                f"Private escrow deal chat for {deal_number}.\n"
                "Managed by EscrowBot — do not share this link with third parties."
            ),
            megagroup=True,
        ))
        group = result.chats[0]
        logger.info(f"[GroupService] Supergroup created: id={group.id} title={group.title}")

        # Export invite link
        invite_result = await client(ExportChatInviteRequest(peer=group))
        invite_link = getattr(invite_result, "link", None)

        if not invite_link:
            raise RuntimeError(
                f"Group was created (id={group.id}) but invite link export returned empty. "
                f"Raw response: {invite_result}"
            )

        logger.info(f"[GroupService] Invite link: {invite_link}")
        return group.id, invite_link

    finally:
        await client.disconnect()


async def create_and_notify_group(
    deal_id: int,
    bot,
    admin_tg_id: int = 0,
) -> None:
    """
    Background task: create a Telegram supergroup for the deal, persist the
    invite link, and notify both buyer and seller.

    On any failure the admin is notified immediately with the exact reason.
    """
    from app.database import AsyncSessionFactory
    from app.services.deal_service import DealService
    from app.services.user_service import UserService
    from aiogram.exceptions import TelegramAPIError

    deal_number = f"deal-{deal_id}"  # fallback label before DB read

    async def _notify_admin(text: str) -> None:
        """Send error/info text to admin — never raises."""
        if not (admin_tg_id and bot):
            return
        try:
            await bot.send_message(admin_tg_id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"[GroupService] Could not notify admin {admin_tg_id}: {e}")

    try:
        # ── 1. Load deal + parties ──────────────────────────────
        async with AsyncSessionFactory() as session:
            deal = await DealService(session).get_by_id(deal_id)
            if not deal:
                logger.warning(f"[GroupService] Deal {deal_id} not found.")
                return
            if deal.chat_invite_link:
                logger.info(f"[GroupService] Group already exists for deal {deal.deal_number}.")
                return

            deal_number = deal.deal_number
            buyer = await UserService(session).get_by_id(deal.buyer_id)
            seller = await UserService(session).get_by_id(deal.seller_id)
            buyer_tg_id = buyer.telegram_id if buyer else None
            seller_tg_id = seller.telegram_id if seller else None

        logger.info(f"[GroupService] Starting group creation for deal {deal_number}…")

        # ── 2. Create the group (outside DB session) ────────────
        group_id, invite_link = await create_deal_group(deal_number)
        logger.info(f"[GroupService] ✅ Group created for {deal_number}: {invite_link}")

        # ── 3. Persist invite link ───────────────────────────────
        async with AsyncSessionFactory() as session:
            deal = await DealService(session).get_by_id(deal_id)
            if deal:
                deal.chat_group_id = group_id
                deal.chat_invite_link = invite_link
                await session.commit()

        # ── 4. Notify both parties ───────────────────────────────
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
                        disable_web_page_preview=False,
                    )
                except TelegramAPIError as e:
                    logger.warning(f"[GroupService] Could not notify user {tg_id}: {e}")

        # ── 5. Also notify admin that it succeeded ───────────────
        await _notify_admin(
            f"✅ <b>Private group created</b> for deal <code>{deal_number}</code>\n"
            f"👉 <a href='{invite_link}'>Group invite link</a>"
        )

    except Exception as e:
        logger.error(f"[GroupService] ❌ Failed to create group for {deal_number}: {e}", exc_info=True)

        error_str = str(e)
        admin_text = (
            f"❌ <b>Private group NOT created</b> for deal <code>{deal_number}</code>\n\n"
            f"<b>Error:</b> <code>{error_str[:500]}</code>\n\n"
        )

        if "SESSION_STRING" in error_str and "invalid or expired" in error_str:
            admin_text += (
                "🔑 Your Telethon session has expired.\n"
                "Re-run the session generation script and update "
                "<code>TELEGRAM_SESSION_STRING</code> in Railway Variables, then redeploy."
            )
        elif "SESSION_STRING" in error_str:
            admin_text += (
                "📋 Set <code>TELEGRAM_SESSION_STRING</code> in Railway Variables.\n"
                "Run locally:\n"
                "<pre>python -c \"\nfrom telethon.sync import TelegramClient\n"
                "from telethon.sessions import StringSession\n"
                "c = TelegramClient(StringSession(), API_ID, 'API_HASH')\n"
                "c.start()\nprint(c.session.save())\n\"</pre>"
            )
        elif "TELEGRAM_API_ID" in error_str or "TELEGRAM_API_HASH" in error_str:
            admin_text += (
                "📋 Set <code>TELEGRAM_API_ID</code> and <code>TELEGRAM_API_HASH</code> "
                "from https://my.telegram.org/apps in Railway Variables."
            )
        else:
            admin_text += (
                "Please check Railway logs for the full traceback.\n"
                "Create the group manually and share the invite link with both parties."
            )

        await _notify_admin(admin_text)
