from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DealStatus(str, enum.Enum):
    PENDING = "pending"                # Created, awaiting seller acceptance
    AWAITING_PAYMENT = "awaiting_payment"  # Seller accepted, buyer must pay
    FUNDED = "funded"                  # Payment confirmed on-chain
    IN_PROGRESS = "in_progress"        # Both parties working
    COMPLETED = "completed"            # Buyer released funds
    CANCELLED = "cancelled"            # Cancelled before funding
    DISPUTED = "disputed"              # Dispute opened
    REFUNDED = "refunded"              # Funds returned to buyer


class Currency(str, enum.Enum):
    USDT_TRC20 = "USDT_TRC20"
    USDT_BEP20 = "USDT_BEP20"
    USDT_ERC20 = "USDT_ERC20"
    USDT_TON   = "USDT_TON"
    BTC        = "BTC"
    ETH        = "ETH"
    BNB        = "BNB"
    LTC        = "LTC"
    DOGE       = "DOGE"
    TRX        = "TRX"
    TON        = "TON"
    FTM        = "FTM"

    @property
    def chain(self) -> str:
        return {
            "USDT_TRC20": "TRON",
            "USDT_BEP20": "BSC",
            "USDT_ERC20": "ETHEREUM",
            "USDT_TON":   "TON",
            "BTC":        "BITCOIN",
            "ETH":        "ETHEREUM",
            "BNB":        "BSC",
            "LTC":        "LITECOIN",
            "DOGE":       "DOGECOIN",
            "TRX":        "TRON",
            "TON":        "TON",
            "FTM":        "FANTOM",
        }[self.value]

    @property
    def symbol(self) -> str:
        return {
            "USDT_TRC20": "USDT",
            "USDT_BEP20": "USDT",
            "USDT_ERC20": "USDT",
            "USDT_TON":   "USDT",
            "BTC":        "BTC",
            "ETH":        "ETH",
            "BNB":        "BNB",
            "LTC":        "LTC",
            "DOGE":       "DOGE",
            "TRX":        "TRX",
            "TON":        "TON",
            "FTM":        "FTM",
        }[self.value]


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    # Parties
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Deal Info
    description: Mapped[str] = mapped_column(Text, nullable=False)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=8), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=18, scale=2), nullable=True)

    # Fees
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=8), default=Decimal("0"), nullable=False)
    fee_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Status
    status: Mapped[DealStatus] = mapped_column(Enum(DealStatus), default=DealStatus.PENDING, nullable=False, index=True)

    # Wallet
    escrow_wallet_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("wallets.id"), nullable=True)

    # Confirmations
    seller_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    buyer_confirmed_completion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Deadline
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_warning_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Cancellation
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cancelled_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Deal Chat (private Telegram supergroup)
    chat_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    chat_invite_link: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Key timestamps
    funded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    buyer: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[buyer_id], back_populates="deals_as_buyer"
    )
    seller: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[seller_id], back_populates="deals_as_seller"
    )
    escrow_wallet: Mapped[Optional["Wallet"]] = relationship(  # noqa: F821
        "Wallet", foreign_keys=[escrow_wallet_id]
    )
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="deal", lazy="select"
    )
    dispute: Mapped[Optional["Dispute"]] = relationship(  # noqa: F821
        "Dispute", back_populates="deal", uselist=False, lazy="select"
    )
    review: Mapped[Optional["Review"]] = relationship(  # noqa: F821
        "Review", back_populates="deal", uselist=False, lazy="select"
    )

    @property
    def is_active(self) -> bool:
        return self.status not in (
            DealStatus.COMPLETED, DealStatus.CANCELLED, DealStatus.REFUNDED
        )

    @property
    def net_amount(self) -> Decimal:
        return self.amount - self.fee_amount

    def __repr__(self) -> str:
        return f"<Deal {self.deal_number} {self.status.value} {self.amount} {self.currency.value}>"
