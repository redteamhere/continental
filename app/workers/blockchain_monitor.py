"""Notify parties when deal transitions to FUNDED (detected by blockchain monitor)."""
from __future__ import annotations

from sqlalchemy import select

from app.database import AsyncSessionFactory
from app.models.deal import Deal, DealStatus
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


# Track which deals we've already notified to avoid double-sending
_notified_funded: set[int] = set()


async def notify_funded_deals(bot=None) -> None:
    """
    Find deals that became FUNDED since last check and send notifications.
    Uses an in-memory set — in production use Redis for persistence across restarts.
    """
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(Deal.status == DealStatus.FUNDED)
        )
        funded_deals = result.scalars().all()

        for deal in funded_deals:
            if deal.id in _notified_funded:
                continue

            _notified_funded.add(deal.id)
            user_svc = UserService(session)
            buyer = await user_svc.get_by_id(deal.buyer_id)
            seller = await user_svc.get_by_id(deal.seller_id)

            notif_svc = NotificationService(session, bot)
            await notif_svc.payment_confirmed(deal, buyer, seller)

        await session.commit()
