from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Chain(str, enum.Enum):
    TRON = "TRON"
    ETHEREUM = "ETHEREUM"
    BSC = "BSC"
    BITCOIN = "BITCOIN"
    LITECOIN = "LITECOIN"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Association (deal wallet or user hot wallet)
    deal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("deals.id"), nullable=True, index=True
    )

    # Chain & Address
    chain: Mapped[Chain] = mapped_column(Enum(Chain), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Encrypted private key — NULL for admin cold wallets (no managed key)
    private_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # HD wallet derivation
    derivation_path: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hd_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Balance tracking
    expected_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=28, scale=8), nullable=True
    )
    confirmed_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=28, scale=8), default=Decimal("0"), nullable=False
    )

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_swept: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    swept_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sweep_tx_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Monitoring
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="wallet", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Wallet chain={self.chain.value} addr={self.address[:12]}...>"
