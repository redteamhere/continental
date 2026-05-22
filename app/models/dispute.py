from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ResolutionType(str, enum.Enum):
    BUYER_REFUND = "buyer_refund"        # Full refund to buyer
    SELLER_RELEASE = "seller_release"    # Full payment to seller
    PARTIAL_SPLIT = "partial_split"      # Split between parties
    NO_ACTION = "no_action"              # No funds moved (e.g., deal was unfunded)


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deals.id"), unique=True, nullable=False, index=True
    )

    # Parties
    opened_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Status
    status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus), default=DisputeStatus.OPEN, nullable=False, index=True
    )

    # Content
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Evidence: list of Telegram file_ids
    evidence_file_ids: Mapped[Optional[List]] = mapped_column(JSON, default=list, nullable=True)

    # Resolution
    resolution_type: Mapped[Optional[ResolutionType]] = mapped_column(
        Enum(ResolutionType), nullable=True
    )
    buyer_split_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    seller_split_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    deal: Mapped["Deal"] = relationship("Deal", back_populates="dispute")  # noqa: F821
    opened_by: Mapped["User"] = relationship("User", foreign_keys=[opened_by_id])  # noqa: F821
    assigned_to: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[assigned_to_id]
    )

    def __repr__(self) -> str:
        return f"<Dispute deal={self.deal_id} status={self.status.value}>"
