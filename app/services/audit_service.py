from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditService:
    """Write-only audit trail. Never modifies existing records."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(
        self,
        action: str,
        user_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        self._s.add(entry)

    # Convenience methods

    async def deal_created(self, user_id: int, deal_id: int, details: dict) -> None:
        await self.log("deal.created", user_id=user_id, target_type="deal", target_id=deal_id, details=details)

    async def deal_funded(self, deal_id: int, tx_hash: str) -> None:
        await self.log("deal.funded", target_type="deal", target_id=deal_id, details={"tx_hash": tx_hash})

    async def deal_completed(self, user_id: int, deal_id: int) -> None:
        await self.log("deal.completed", user_id=user_id, target_type="deal", target_id=deal_id)

    async def deal_cancelled(self, user_id: int, deal_id: int, reason: str) -> None:
        await self.log("deal.cancelled", user_id=user_id, target_type="deal", target_id=deal_id, details={"reason": reason})

    async def dispute_opened(self, user_id: int, deal_id: int, reason: str) -> None:
        await self.log("dispute.opened", user_id=user_id, target_type="deal", target_id=deal_id, details={"reason": reason})

    async def dispute_resolved(self, admin_id: int, dispute_id: int, resolution: str) -> None:
        await self.log("dispute.resolved", user_id=admin_id, target_type="dispute", target_id=dispute_id, details={"resolution": resolution})

    async def user_banned(self, admin_id: int, target_user_id: int, reason: str) -> None:
        await self.log("user.banned", user_id=admin_id, target_type="user", target_id=target_user_id, details={"reason": reason})

    async def pin_set(self, user_id: int) -> None:
        await self.log("user.pin_set", user_id=user_id)

    async def pin_failed(self, user_id: int) -> None:
        await self.log("user.pin_failed", user_id=user_id)

    async def admin_action(self, admin_id: int, action: str, details: dict) -> None:
        await self.log(f"admin.{action}", user_id=admin_id, details=details)
