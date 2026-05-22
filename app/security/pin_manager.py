"""PIN hashing and verification with brute-force protection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext

# bcrypt with a high work factor
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


class PinManager:
    @staticmethod
    def hash_pin(pin: str) -> str:
        """Return bcrypt hash of a 4–8 digit PIN."""
        if not pin.isdigit() or not (4 <= len(pin) <= 8):
            raise ValueError("PIN must be 4–8 digits")
        return _pwd_ctx.hash(pin)

    @staticmethod
    def verify_pin(pin: str, pin_hash: str) -> bool:
        """Verify PIN against stored hash. Safe against timing attacks."""
        return _pwd_ctx.verify(pin, pin_hash)

    @staticmethod
    def is_locked(pin_locked_until: Optional[datetime]) -> bool:
        """Return True if the account is currently locked out."""
        if pin_locked_until is None:
            return False
        return datetime.now(timezone.utc) < pin_locked_until

    @staticmethod
    def lockout_until() -> datetime:
        """Calculate the unlock timestamp after max failed attempts."""
        return datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)

    @staticmethod
    def should_lock(attempts: int) -> bool:
        return attempts >= MAX_ATTEMPTS

    @staticmethod
    def seconds_until_unlock(pin_locked_until: Optional[datetime]) -> int:
        if pin_locked_until is None:
            return 0
        delta = pin_locked_until - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))
