from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.security.pin_manager import PinManager


def _make_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self._s.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        clean = username.lstrip("@").lower()
        result = await self._s.execute(
            select(User).where(User.username == clean)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self._s.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        result = await self._s.execute(
            select(User).where(User.referral_code == code.upper())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        first_name: str,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        language_code: str = "en",
        referral_code_used: Optional[str] = None,
    ) -> User:
        referred_by_id = None
        if referral_code_used:
            referrer = await self.get_by_referral_code(referral_code_used)
            if referrer and referrer.telegram_id != telegram_id:
                referred_by_id = referrer.id

        # Ensure unique referral code
        while True:
            code = _make_referral_code()
            existing = await self.get_by_referral_code(code)
            if not existing:
                break

        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username.lstrip("@").lower() if username else None,
            language_code=language_code,
            referral_code=code,
            referred_by_id=referred_by_id,
        )
        self._s.add(user)
        await self._s.flush()
        return user

    async def set_pin(self, user: User, pin: str) -> None:
        user.pin_hash = PinManager.hash_pin(pin)
        user.pin_attempts = 0
        user.pin_locked_until = None

    async def reset_pin(self, user: User) -> None:
        """Clear PIN so the user must create a new one."""
        user.pin_hash = None
        user.pin_attempts = 0
        user.pin_locked_until = None

    async def verify_pin(self, user: User, pin: str) -> bool:
        """Verify PIN with lockout protection. Returns True on success."""
        if PinManager.is_locked(user.pin_locked_until):
            return False

        if not user.pin_hash:
            return False

        ok = PinManager.verify_pin(pin, user.pin_hash)
        if ok:
            user.pin_attempts = 0
            user.pin_locked_until = None
            return True

        user.pin_attempts += 1
        if PinManager.should_lock(user.pin_attempts):
            user.pin_locked_until = PinManager.lockout_until()
            user.pin_attempts = 0
        return False

    async def update_last_active(self, user: User) -> None:
        user.last_active = datetime.now(timezone.utc)

    async def update_username(self, user: User, username: Optional[str]) -> None:
        user.username = username.lstrip("@").lower() if username else None

    async def ban(self, user: User, reason: str, admin: User) -> None:
        user.is_banned = True
        user.ban_reason = reason

    async def unban(self, user: User) -> None:
        user.is_banned = False
        user.ban_reason = None

    async def set_role(self, user: User, role: UserRole) -> None:
        user.role = role

    async def count_total(self) -> int:
        """Total registered users."""
        from sqlalchemy import func as sqlfunc
        result = await self._s.execute(select(sqlfunc.count(User.id)))
        return result.scalar_one() or 0

    async def count_monthly_active(self) -> int:
        """Users who interacted with the bot in the last 30 days."""
        from datetime import timedelta
        from sqlalchemy import func as sqlfunc
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = await self._s.execute(
            select(sqlfunc.count(User.id)).where(User.last_active >= cutoff)
        )
        return result.scalar_one() or 0

    async def recalculate_reputation(self, user: User) -> None:
        """Recompute reputation from all received reviews."""
        from sqlalchemy import func as sqlfunc
        from app.models.audit import Review
        result = await self._s.execute(
            select(sqlfunc.avg(Review.rating), sqlfunc.count(Review.id))
            .where(Review.reviewee_id == user.id)
        )
        avg_rating, count = result.one()
        if count and count > 0:
            user.reputation_score = float(avg_rating)
        else:
            user.reputation_score = 5.0
