"""Cancel overdue deals and send deadline warnings."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionFactory
from app.models.deal import Deal, DealStatus
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


async def expire_overdue_deals() -> None:
    """Cancel any deal that has passed its deadline without being funded."""
    now = datetime.now(timezone.utc)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(
                Deal.status.in_([DealStatus.PENDING, DealStatus.AWAITING_PAYMENT]),
                Deal.deadline < now,
                Deal.deadline.isnot(None),
            )
        )
        deals = result.scalars().all()

        if not deals:
            return

        logger.info(f"[Expiry] Expiring {len(deals)} overdue deal(s)")
        for deal in deals:
            deal.status = DealStatus.CANCELLED
            deal.cancellation_reason = "Expired: deadline passed without payment"
            deal.cancelled_at = now

        await session.commit()
        logger.info(f"[Expiry] Expired {len(deals)} deal(s)")


async def send_expiry_warnings(bot=None) -> None:
    """Send 24-hour warning for deals approaching deadline."""
    warning_threshold = datetime.now(timezone.utc) + timedelta(
        hours=settings.DEAL_EXPIRY_WARNING_HOURS
    )
    now = datetime.now(timezone.utc)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Deal).where(
                Deal.status.in_([DealStatus.AWAITING_PAYMENT, DealStatus.FUNDED, DealStatus.IN_PROGRESS]),
                Deal.deadline <= warning_threshold,
                Deal.deadline > now,
                Deal.expiry_warning_sent == False,
                Deal.deadline.isnot(None),
            )
        )
        deals = result.scalars().all()

        if not deals:
            return

        logger.info(f"[Expiry] Sending warnings for {len(deals)} deal(s)")
        notif_svc = NotificationService(session, bot)
        user_svc = UserService(session)

        for deal in deals:
            buyer = await user_svc.get_by_id(deal.buyer_id)
            seller = await user_svc.get_by_id(deal.seller_id)
            await notif_svc.deadline_warning(deal, buyer, seller)
            deal.expiry_warning_sent = True

        await session.commit()
