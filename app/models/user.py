from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Auth
    pin_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    pin_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pin_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Role & Status
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Referral
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    referred_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Stats
    reputation_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    total_deals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sales: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_disputes_opened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_disputes_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # KYC
    kyc_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Language
    language_code: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    deals_as_buyer: Mapped[List["Deal"]] = relationship(  # noqa: F821
        "Deal", foreign_keys="Deal.buyer_id", back_populates="buyer", lazy="select"
    )
    deals_as_seller: Mapped[List["Deal"]] = relationship(  # noqa: F821
        "Deal", foreign_keys="Deal.seller_id", back_populates="seller", lazy="select"
    )
    reviews_given: Mapped[List["Review"]] = relationship(  # noqa: F821
        "Review", foreign_keys="Review.reviewer_id", back_populates="reviewer", lazy="select"
    )
    reviews_received: Mapped[List["Review"]] = relationship(  # noqa: F821
        "Review", foreign_keys="Review.reviewee_id", back_populates="reviewee", lazy="select"
    )
    notifications: Mapped[List["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="user", lazy="select"
    )

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.first_name

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_moderator(self) -> bool:
        return self.role in (UserRole.MODERATOR, UserRole.ADMIN)

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id} @{self.username}>"
