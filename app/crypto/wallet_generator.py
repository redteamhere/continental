"""
HD wallet generation for TRON, Ethereum, Bitcoin, Litecoin.

In LOCAL_DEV mode: generates deterministic fake addresses so the full bot
flow (deal creation, payment UI, etc.) can be tested without installing
C-extension packages (bip-utils, web3) that require a compiler.

In production: set LOCAL_DEV=false and ensure bip-utils==2.9.3 is installed.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from app.models.wallet import Chain


@dataclass(frozen=True)
class GeneratedWallet:
    chain: Chain
    address: str
    private_key: str       # hex — encrypt before persisting
    derivation_path: str


class WalletGenerator:
    def __init__(self, master_mnemonic: str) -> None:
        self._mnemonic = master_mnemonic

    @staticmethod
    def generate_mnemonic() -> str:
        """Generate a placeholder mnemonic for local dev."""
        if os.environ.get("LOCAL_DEV", "true").lower() == "true":
            return "test " * 23 + "test"
        # Production: use bip_utils
        from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum
        return str(Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24))

    def derive_wallet(self, chain: Chain, index: int) -> GeneratedWallet:
        if os.environ.get("LOCAL_DEV", "true").lower() == "true":
            return self._derive_mock(chain, index)
        return self._derive_real(chain, index)

    def _derive_mock(self, chain: Chain, index: int) -> GeneratedWallet:
        """Deterministic mock wallet — same input always gives same output."""
        seed = f"{self._mnemonic}:{chain.value}:{index}".encode()
        h = hashlib.sha256(seed).hexdigest()
        private_key = h  # 64-char hex — not a real key

        if chain == Chain.TRON:
            # TRON addresses start with T and are 34 chars
            address = "T" + h[:33].upper()
        elif chain == Chain.ETHEREUM:
            address = "0x" + h[:40]
        elif chain == Chain.BITCOIN:
            address = "bc1q" + h[:36]
        elif chain == Chain.LITECOIN:
            address = "ltc1q" + h[:35]
        else:
            address = h[:42]

        path = f"m/44'/0'/0'/0/{index}"
        return GeneratedWallet(chain=chain, address=address, private_key=private_key, derivation_path=path)

    def _derive_real(self, chain: Chain, index: int) -> GeneratedWallet:
        """Real BIP-44 derivation — requires bip-utils to be installed."""
        from bip_utils import (
            Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes, Bip39WordsNum
        )
        _BIP44_COIN = {
            Chain.ETHEREUM: Bip44Coins.ETHEREUM,
            Chain.BITCOIN: Bip44Coins.BITCOIN,
            Chain.LITECOIN: Bip44Coins.LITECOIN,
            Chain.TRON: Bip44Coins.TRON,
        }
        seed = Bip39SeedGenerator(self._mnemonic).Generate()
        coin = _BIP44_COIN[chain]
        bip44_addr = (
            Bip44.FromSeed(seed, coin)
            .Purpose().Coin().Account(0)
            .Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(index)
        )
        return GeneratedWallet(
            chain=chain,
            address=bip44_addr.PublicKey().ToAddress(),
            private_key=bip44_addr.PrivateKey().Raw().ToHex(),
            derivation_path=f"m/44'/0'/0'/0/{index}",
        )
