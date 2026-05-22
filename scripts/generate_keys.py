"""
Run once to generate secure keys for your .env file.
Usage: python scripts/generate_keys.py
"""
import secrets

print("=" * 60)
print("EscrowBot — Secure Key Generator")
print("=" * 60)
print()
print("Copy these into your .env file:")
print()
print(f"SECRET_KEY={secrets.token_hex(32)}")
print(f"ENCRYPTION_KEY={secrets.token_hex(32)}")
print(f"BOT_WEBHOOK_SECRET={secrets.token_hex(24)}")
print()

try:
    from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum
    mnemonic = Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24)
    print("=" * 60)
    print("MASTER MNEMONIC — STORE OFFLINE, NEVER SHARE:")
    print("=" * 60)
    print(f"MASTER_MNEMONIC={mnemonic}")
    print()
    print("⚠️  This mnemonic controls ALL escrow wallets.")
    print("    Back it up on paper and store securely.")
except ImportError:
    print("Install bip_utils first: pip install bip-utils==2.9.3")
