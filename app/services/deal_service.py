from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.deal import Deal, DealStatus, Currency
from app.models.user import User
from app.models.wallet import Wallet, Chain


def _generate_deal_number() -> str:
    """e.g. ESC-A3F2B9"""
    suffix = secrets.token_hex(3).upper()
    return f"ESC-{suffix}"


def _calculate_fee(amount: Decimal) -> Decimal:
    return (amount * Decimal(str(settings.ESCROW_FEE_PERCENT)) / Decimal("100")).quantize(
        Decimal("0.00000001")
    )


class DealService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        buyer: User,
        seller: User,
        description: str,
        amount: Decimal,
        currency: Currency,
        deadline_days: int,
        terms: Optional[str] = None,
    ) -> Deal:
        # Unique deal number
        while True:
            number = _generate_deal_number()
            existing = await self._s.execute(
                select(Deal).where(Deal.deal_number == number)
            )
            if not existing.scalar_one_or_none():
                break

        fee = _calculate_fee(amount)
        deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)

        deal = Deal(
            deal_number=number,
            buyer_id=buyer.id,
            seller_id=seller.id,
            description=description,
            amount=amount,
            currency=currency,
            fee_amount=fee,
            terms=terms,
            deadline=deadline,
            status=DealStatus.PENDING,
        )
        self._s.add(deal)
        await self._s.flush()
        return deal

    async def get_by_number(self, deal_number: str) -> Optional[Deal]:
        result = await self._s.execute(
            select(Deal).where(Deal.deal_number == deal_number.upper())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, deal_id: int) -> Optional[Deal]:
        result = await self._s.execute(select(Deal).where(Deal.id == deal_id))
        return result.scalar_one_or_none()

    async def get_user_deals(
        self, user: User, status: Optional[DealStatus] = None, limit: int = 10, offset: int = 0
    ) -> list[Deal]:
        conditions = [
            (Deal.buyer_id == user.id) | (Deal.seller_id == user.id)
        ]
        if status:
            conditions.append(Deal.status == status)

        result = await self._s.execute(
            select(Deal)
            .where(and_(*conditions))
            .order_by(Deal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def accept_by_seller(self, deal: Deal, seller: User) -> None:
        """Seller accepts the deal — moves to AWAITING_PAYMENT."""
        if deal.seller_id != seller.id:
            raise PermissionError("Only the seller can accept this deal")
        if deal.status != DealStatus.PENDING:
            raise ValueError(f"Deal must be PENDING to accept, got {deal.status.value}")
        deal.seller_accepted = True
        deal.status = DealStatus.AWAITING_PAYMENT

    async def attach_wallet(self, deal: Deal, wallet: Wallet) -> None:
        deal.escrow_wallet_id = wallet.id

    async def mark_funded(self, deal: Deal) -> None:
        deal.status = DealStatus.FUNDED
        deal.funded_at = datetime.now(timezone.utc)

    async def start_progress(self, deal: Deal) -> None:
        if deal.status != DealStatus.FUNDED:
            raise ValueError("Deal must be FUNDED to start progress")
        deal.status = DealStatus.IN_PROGRESS

    async def complete(self, deal: Deal, buyer: User) -> None:
        if deal.buyer_id != buyer.id:
            raise PermissionError("Only the buyer can release funds")
        if deal.status not in (DealStatus.FUNDED, DealStatus.IN_PROGRESS):
            raise ValueError(f"Cannot complete deal in status {deal.status.value}")
        deal.status = DealStatus.COMPLETED
        deal.buyer_confirmed_completion = True
        deal.completed_at = datetime.now(timezone.utc)

        # Update stats
        buyer_user = await self._s.get(User, deal.buyer_id)
        seller_user = await self._s.get(User, deal.seller_id)
        if buyer_user:
            buyer_user.total_deals += 1
            buyer_user.total_purchases += 1
        if seller_user:
            seller_user.total_deals += 1
            seller_user.total_sales += 1

    async def cancel(
        self, deal: Deal, cancelled_by: User, reason: Optional[str] = None
    ) -> None:
        if deal.status in (DealStatus.COMPLETED, DealStatus.CANCELLED, DealStatus.REFUNDED):
            raise ValueError("Deal already finalized")
        if deal.status == DealStatus.FUNDED and cancelled_by.id not in (deal.buyer_id, deal.seller_id):
            raise PermissionError("Only parties can cancel a funded deal")
        deal.status = DealStatus.CANCELLED
        deal.cancelled_at = datetime.now(timezone.utc)
        deal.cancelled_by_id = cancelled_by.id
        deal.cancellation_reason = reason or "Cancelled by user"

    async def open_dispute(self, deal: Deal, opened_by: User, reason: str) -> None:
        if deal.status not in (DealStatus.FUNDED, DealStatus.IN_PROGRESS):
            raise ValueError("Can only dispute funded or in-progress deals")
        if opened_by.id not in (deal.buyer_id, deal.seller_id):
            raise PermissionError("Only deal parties can open a dispute")
        deal.status = DealStatus.DISPUTED

    async def refund(self, deal: Deal) -> None:
        deal.status = DealStatus.REFUNDED

    async def count_today_deals(self, user: User) -> int:
        from sqlalchemy import func
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._s.execute(
            select(func.count(Deal.id)).where(
                Deal.buyer_id == user.id,
                Deal.created_at >= today,
            )
        )
        return result.scalar_one() or 0
