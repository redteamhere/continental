"""Deal chat — opens a real private Telegram supergroup for buyer and seller."""
from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data.startswith("deal:chat:"))
async def show_deal_chat(callback: CallbackQuery, db_user) -> None:
    from app.database import AsyncSessionFactory
    from app.services.deal_service import DealService
    from app.models.deal import DealStatus

    deal_id = int(callback.data.split(":")[2])

    async with AsyncSessionFactory() as session:
        deal = await DealService(session).get_by_id(deal_id)

        if not deal:
            await callback.answer("Deal not found.", show_alert=True)
            return

        if deal.status not in (DealStatus.FUNDED, DealStatus.IN_PROGRESS):
            await callback.answer(
                "Deal chat is only available for funded or active deals.",
                show_alert=True,
            )
            return

        if db_user.id not in (deal.buyer_id, deal.seller_id):
            await callback.answer("You are not a party to this deal.", show_alert=True)
            return

        invite_link = deal.chat_invite_link
        deal_number = deal.deal_number
        deal_db_id = deal.id

    if invite_link:
        await callback.message.answer(
            f"💬 <b>Private Deal Chat</b>\n\n"
            f"Deal: <code>{deal_number}</code>\n\n"
            f"👉 <a href='{invite_link}'>Join your private group</a>\n\n"
            f"You and your counterpart can talk, share files, and coordinate "
            f"freely inside this group.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    # Group not yet created — create it now in background
    await callback.message.answer(
        "⏳ <b>Creating your private group...</b>\n\n"
        "This takes a few seconds. You will receive the join link shortly.",
        parse_mode="HTML",
    )
    await callback.answer()

    from app.services.group_service import create_and_notify_group
    asyncio.create_task(create_and_notify_group(deal_db_id, callback.bot))
