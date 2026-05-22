from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TxStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(Integer, ForeignKey("deals.id"), nullable=False, index=True)
    wallet_id: Mapped[int] = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False, index=True)

    tx_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    from_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    to_address: Mapped[str] = mapped_column(String(128), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=8), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)

    confirmations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_confirmations: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[TxStatus] = mapped_column(
        Enum(TxStatus), default=TxStatus.PENDING, nullable=False, index=True
    )

    block_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    block_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Gas / fee info (for ETH etc.)
    gas_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=28, scale=18), nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    deal: Mapped["Deal"] = relationship("Deal", back_populates="transactions")  # noqa: F821
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Tx hash={self.tx_hash[:16]}... {self.status.value} {self.amount} {self.currency}>"
