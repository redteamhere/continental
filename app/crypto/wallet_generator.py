"""
HD wallet generation for TRON, Ethereum, Bitcoin, Litecoin.
Uses BIP-39 (mnemonic) + BIP-44 (derivation paths).
Private keys are NEVER stored in plaintext — always encrypted on write.
"""
from __future__ import annotations

from dataclasses import dataclass

from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    Bip39WordsNum,
)

from app.models.wallet import Chain


@dataclass(frozen=True)
class GeneratedWallet:
    chain: Chain
    address: str
    private_key: str       # hex string — encrypt before persisting
    derivation_path: str


# BIP-44 coin mapping
_BIP44_COIN: dict[Chain, Bip44Coins] = {
    Chain.ETHEREUM: Bip44Coins.ETHEREUM,
    Chain.BITCOIN: Bip44Coins.BITCOIN,
    Chain.LITECOIN: Bip44Coins.LITECOIN,
    Chain.TRON: Bip44Coins.TRON,
}


class WalletGenerator:
    """
    Generates deterministic HD wallets per deal.
    Each deal gets a unique index so wallets are reproducible from the master seed.
    The master mnemonic must be stored securely (encrypted, offline backup).
    """

    def __init__(self, master_mnemonic: str) -> None:
        self._mnemonic = master_mnemonic
        self._seed = Bip39SeedGenerator(master_mnemonic).Generate()

    @staticmethod
    def generate_mnemonic() -> str:
        """Generate a new 24-word BIP-39 mnemonic (256-bit entropy)."""
        return Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24)

    def derive_wallet(self, chain: Chain, index: int) -> GeneratedWallet:
        """Derive wallet at m/44'/<coin>'/0'/0/<index>."""
        coin = _BIP44_COIN[chain]
        bip44_mst = Bip44.FromSeed(self._seed, coin)
        bip44_acc = bip44_mst.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT)
        bip44_addr = bip44_acc.AddressIndex(index)

        private_key = bip44_addr.PrivateKey().Raw().ToHex()
        address = bip44_addr.PublicKey().ToAddress()
        derivation_path = f"m/44'/{_coin_type(coin)}'/0'/0/{index}"

        # TRON addresses use Base58 starting with 'T'
        # ETH uses '0x' prefix — bip_utils handles both
        return GeneratedWallet(
            chain=chain,
            address=address,
            private_key=private_key,
            derivation_path=derivation_path,
        )


def _coin_type(coin: Bip44Coins) -> int:
    mapping = {
        Bip44Coins.ETHEREUM: 60,
        Bip44Coins.BITCOIN: 0,
        Bip44Coins.LITECOIN: 2,
        Bip44Coins.TRON: 195,
    }
    return mapping.get(coin, 0)
