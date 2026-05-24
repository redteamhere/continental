"""Notify parties when deal transitions to FUNDED (detected by blockchain monitor)."""
from __future__ import annotations

from sqlalchemy import select

from app.database import AsyncSessionFactory
from app.models.audit import Notification
from app.models.deal import Deal, DealStatus
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


async def notify_funded_deals(bot=None) -> None:
    """
    Find FUNDED deals that haven't been notified yet and send payment_confirmed.
    Uses the Notification DB table for deduplication — persistent across restarts.
    """
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(Deal.status == DealStatus.FUNDED)
        )
        funded_deals = result.scalars().all()

        for deal in funded_deals:
            # Check DB: skip if a funds_confirmed notification already exists for this deal
            existing = await session.execute(
                select(Notification.id).where(
                    Notification.type == "funds_confirmed",
                    Notification.deal_id == deal.id,
                ).limit(1)
            )
            if existing.scalar():
                continue  # Already notified (by admin confirm or a previous scheduler run)

            user_svc = UserService(session)
            buyer = await user_svc.get_by_id(deal.buyer_id)
            seller = await user_svc.get_by_id(deal.seller_id)

            notif_svc = NotificationService(session, bot)
            await notif_svc.payment_confirmed(deal, buyer, seller)

        await session.commit()
