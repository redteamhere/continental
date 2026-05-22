"""
Blockchain monitoring service.
Polls all active escrow wallets and updates deal status when payment is detected.
Runs as a background worker via APScheduler.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import os

from app.config import settings
from app.database import AsyncSessionFactory
from app.models.deal import Deal, DealStatus, Currency
from app.models.transaction import Transaction, TxStatus
from app.models.wallet import Chain, Wallet
from app.security.encryption import decrypt_private_key

_LOCAL_DEV = os.environ.get("LOCAL_DEV", "true").lower() == "true"

if not _LOCAL_DEV:
    from app.crypto.btc_client import BlockClient
    from app.crypto.eth_client import EthClient
    from app.crypto.tron_client import TronClient


class BlockchainMonitor:
    """Poll active wallets and detect incoming payments."""

    def __init__(self) -> None:
        self._local_dev = _LOCAL_DEV
        if not self._local_dev:
            self._tron = TronClient()
            self._eth = EthClient()
            self._btc = BlockClient("BTC")
            self._ltc = BlockClient("LTC")

    async def run_cycle(self) -> None:
        """One full monitoring pass across all active wallets."""
        if self._local_dev:
            logger.debug("[Monitor] LOCAL_DEV mode — blockchain monitoring skipped")
            return
        async with AsyncSessionFactory() as session:
            wallets = await self._get_active_wallets(session)
            logger.info(f"[Monitor] Checking {len(wallets)} active wallets")
            tasks = [self._check_wallet(session, w) for w in wallets]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"[Monitor] Wallet check error: {r}")

    async def _get_active_wallets(self, session: AsyncSession) -> list[Wallet]:
        stmt = (
            select(Wallet)
            .join(Deal, Deal.escrow_wallet_id == Wallet.id)
            .where(
                Wallet.is_active == True,
                Wallet.is_swept == False,
                Deal.status.in_([DealStatus.AWAITING_PAYMENT, DealStatus.FUNDED, DealStatus.IN_PROGRESS]),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _check_wallet(self, session: AsyncSession, wallet: Wallet) -> None:
        try:
            if wallet.chain == Chain.TRON:
                await self._check_tron(session, wallet)
            elif wallet.chain == Chain.ETHEREUM:
                await self._check_eth(session, wallet)
            elif wallet.chain == Chain.BITCOIN:
                await self._check_btc(session, wallet)
            elif wallet.chain == Chain.LITECOIN:
                await self._check_ltc(session, wallet)

            wallet.last_checked_at = datetime.now(timezone.utc)
            wallet.check_count += 1
            await session.commit()
        except Exception as e:
            logger.warning(f"[Monitor] Error checking wallet {wallet.id}: {e}")
            await session.rollback()

    async def _check_tron(self, session: AsyncSession, wallet: Wallet) -> None:
        deal = await self._get_deal(session, wallet)
        if not deal:
            return

        since_ms = int(deal.created_at.timestamp() * 1000) if deal.created_at else 0
        txs = await self._tron.get_incoming_usdt_tx(wallet.address, min_timestamp_ms=since_ms)

        for tx_data in txs:
            await self._record_transaction(
                session, deal, wallet, tx_data,
                required=settings.USDT_TRC20_CONFIRMATIONS,
            )

    async def _check_eth(self, session: AsyncSession, wallet: Wallet) -> None:
        deal = await self._get_deal(session, wallet)
        if not deal:
            return

        from_block = 0
        txs = await self._eth.get_incoming_txs(wallet.address, from_block=from_block)
        for tx_data in txs:
            await self._record_transaction(
                session, deal, wallet, tx_data,
                required=settings.ETH_CONFIRMATIONS,
            )

    async def _check_btc(self, session: AsyncSession, wallet: Wallet) -> None:
        deal = await self._get_deal(session, wallet)
        if not deal:
            return

        txs = await self._btc.get_transactions(wallet.address)
        for tx_data in txs:
            await self._record_transaction(
                session, deal, wallet, tx_data,
                required=settings.BTC_CONFIRMATIONS,
            )

    async def _check_ltc(self, session: AsyncSession, wallet: Wallet) -> None:
        deal = await self._get_deal(session, wallet)
        if not deal:
            return

        txs = await self._ltc.get_transactions(wallet.address)
        for tx_data in txs:
            await self._record_transaction(
                session, deal, wallet, tx_data,
                required=settings.LTC_CONFIRMATIONS,
            )

    async def _record_transaction(
        self,
        session: AsyncSession,
        deal: Deal,
        wallet: Wallet,
        tx_data: dict,
        required: int,
    ) -> None:
        tx_hash = tx_data["tx_hash"]

        # Duplicate prevention
        existing = await session.execute(
            select(Transaction).where(Transaction.tx_hash == tx_hash)
        )
        existing_tx = existing.scalar_one_or_none()

        confirmations = tx_data.get("confirmations", 0)
        amount = tx_data["amount"]

        if existing_tx:
            # Update confirmation count only
            if existing_tx.status == TxStatus.CONFIRMED:
                return
            existing_tx.confirmations = confirmations
            if confirmations >= required:
                existing_tx.status = TxStatus.CONFIRMED
                existing_tx.confirmed_at = datetime.now(timezone.utc)
                await self._on_payment_confirmed(session, deal, wallet, amount)
            return

        # New transaction
        status = TxStatus.CONFIRMED if confirmations >= required else TxStatus.CONFIRMING
        new_tx = Transaction(
            deal_id=deal.id,
            wallet_id=wallet.id,
            tx_hash=tx_hash,
            from_address=tx_data.get("from_address"),
            to_address=tx_data["to_address"],
            amount=amount,
            currency=deal.currency.value,
            confirmations=confirmations,
            required_confirmations=required,
            status=status,
            block_number=tx_data.get("block_number"),
            confirmed_at=datetime.now(timezone.utc) if status == TxStatus.CONFIRMED else None,
        )
        session.add(new_tx)

        if status == TxStatus.CONFIRMED:
            await self._on_payment_confirmed(session, deal, wallet, amount)
        else:
            logger.info(
                f"[Monitor] Unconfirmed tx {tx_hash[:16]}... "
                f"for deal {deal.deal_number}: {confirmations}/{required} confirms"
            )

    async def _on_payment_confirmed(
        self,
        session: AsyncSession,
        deal: Deal,
        wallet: Wallet,
        amount: Decimal,
    ) -> None:
        if deal.status == DealStatus.FUNDED:
            return  # Already funded

        wallet.confirmed_balance += amount

        # Check if sufficient (allow small rounding tolerance of 0.01%)
        expected = deal.amount
        tolerance = expected * Decimal("0.0001")
        if wallet.confirmed_balance >= (expected - tolerance):
            deal.status = DealStatus.FUNDED
            deal.funded_at = datetime.now(timezone.utc)
            logger.info(
                f"[Monitor] Deal {deal.deal_number} FUNDED "
                f"({wallet.confirmed_balance} {deal.currency.value})"
            )
            # Notification is handled by the notification worker watching for FUNDED deals
        else:
            logger.info(
                f"[Monitor] Partial payment for deal {deal.deal_number}: "
                f"{wallet.confirmed_balance}/{expected} {deal.currency.value}"
            )

    async def _get_deal(self, session: AsyncSession, wallet: Wallet) -> Deal | None:
        stmt = select(Deal).where(Deal.escrow_wallet_id == wallet.id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
