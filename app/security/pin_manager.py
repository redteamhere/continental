"""PIN hashing and verification using bcrypt directly (passlib-free)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
_ROUNDS = 12


class PinManager:
    @staticmethod
    def hash_pin(pin: str) -> str:
        if not pin.isdigit() or not (4 <= len(pin) <= 8):
            raise ValueError("PIN must be 4–8 digits")
        salt = bcrypt.gensalt(rounds=_ROUNDS)
        hashed = bcrypt.hashpw(pin.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_pin(pin: str, pin_hash: str) -> bool:
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def is_locked(pin_locked_until: Optional[datetime]) -> bool:
        if pin_locked_until is None:
            return False
        return datetime.now(timezone.utc) < pin_locked_until

    @staticmethod
    def lockout_until() -> datetime:
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
