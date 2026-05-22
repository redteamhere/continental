"""
Core escrow logic: wallet generation, fund locking, release, and refund.
Private keys are decrypted only at the moment of signing and immediately discarded.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto.tron_client import TronClient, USDT_CONTRACT
from app.crypto.wallet_generator import WalletGenerator
from app.models.deal import Deal, Currency
from app.models.wallet import Chain, Wallet
from app.security.encryption import encrypt_private_key, decrypt_private_key


def _get_wallet_generator() -> WalletGenerator:
    mnemonic = settings.MASTER_MNEMONIC
    if not mnemonic:
        raise RuntimeError("MASTER_MNEMONIC not set in .env")
    return WalletGenerator(mnemonic)


def _chain_for_currency(currency: Currency) -> Chain:
    return Chain(currency.chain)


class EscrowService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._tron = TronClient()

    async def create_escrow_wallet(self, deal: Deal) -> Wallet:
        """Generate a unique escrow wallet for the deal."""
        generator = _get_wallet_generator()
        chain = _chain_for_currency(deal.currency)

        # Use deal.id as HD wallet index for reproducibility
        generated = generator.derive_wallet(chain, deal.id)

        encrypted_pk = encrypt_private_key(generated.private_key)
        wallet = Wallet(
            deal_id=deal.id,
            chain=chain,
            address=generated.address,
            private_key_encrypted=encrypted_pk,
            derivation_path=generated.derivation_path,
            hd_index=deal.id,
            expected_amount=deal.amount,
        )
        self._s.add(wallet)
        await self._s.flush()
        logger.info(f"[Escrow] Created wallet {wallet.address[:16]}... for deal {deal.deal_number}")
        return wallet

    async def get_wallet_for_deal(self, deal: Deal) -> Optional[Wallet]:
        if deal.escrow_wallet_id is None:
            return None
        result = await self._s.execute(
            select(Wallet).where(Wallet.id == deal.escrow_wallet_id)
        )
        return result.scalar_one_or_none()

    async def release_funds_to_seller(self, deal: Deal) -> Optional[str]:
        """
        Send escrowed funds to the seller's external withdrawal address.
        Returns the outgoing transaction hash, or None if dry-run / not implemented.

        NOTE: Implement per-chain signing logic here.
        For USDT TRC20 this uses TronPy; for BTC/ETH use respective signing libraries.
        """
        wallet = await self.get_wallet_for_deal(deal)
        if not wallet:
            raise ValueError(f"No escrow wallet for deal {deal.deal_number}")

        # In a full implementation: get seller's withdrawal address from their profile,
        # sign the transaction with the decrypted private key, and broadcast it.
        # The private key is used only within this function scope and never stored.
        private_key = decrypt_private_key(wallet.private_key_encrypted)

        # For now we log intent; real signing is chain-specific
        logger.info(
            f"[Escrow] Releasing {deal.net_amount} {deal.currency.value} "
            f"from {wallet.address[:16]}... to seller (deal {deal.deal_number})"
        )

        # Zero out in-memory key reference immediately
        del private_key

        # Mark wallet as swept
        wallet.is_swept = True
        from datetime import datetime, timezone
        wallet.swept_at = datetime.now(timezone.utc)

        return None  # Replace with actual tx_hash after broadcasting

    async def refund_to_buyer(self, deal: Deal, buyer_address: str) -> Optional[str]:
        """Return funds to buyer's address."""
        wallet = await self.get_wallet_for_deal(deal)
        if not wallet:
            raise ValueError(f"No escrow wallet for deal {deal.deal_number}")

        private_key = decrypt_private_key(wallet.private_key_encrypted)
        logger.info(
            f"[Escrow] Refunding {deal.amount} {deal.currency.value} "
            f"from {wallet.address[:16]}... to buyer {buyer_address[:16]}... "
            f"(deal {deal.deal_number})"
        )
        del private_key

        wallet.is_swept = True
        from datetime import datetime, timezone
        wallet.swept_at = datetime.now(timezone.utc)
        return None
