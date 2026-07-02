"""AES-256-GCM encryption for sensitive data (private keys, etc.)."""
from __future__ import annotations

import base64
import os
from typing import Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    """Derive 32-byte key from config."""
    key_hex = settings.ENCRYPTION_KEY
    if len(key_hex) < 64:
        raise ValueError("ENCRYPTION_KEY must be at least 64 hex characters (32 bytes)")
    return bytes.fromhex(key_hex[:64])


def encrypt(plaintext: Union[str, bytes]) -> str:
    """Encrypt data with AES-256-GCM. Returns base64-encoded nonce+ciphertext."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Prepend nonce to ciphertext then base64-encode
    combined = nonce + ciphertext
    return base64.urlsafe_b64encode(combined).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt AES-256-GCM token. Returns plaintext string."""
    key = _get_key()
    aesgcm = AESGCM(key)
    # Restore stripped base64 padding before decoding
    padded = token + "=" * (-len(token) % 4)
    combined = base64.urlsafe_b64decode(padded.encode("ascii"))
    nonce = combined[:12]
    ciphertext = combined[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def encrypt_private_key(private_key: str) -> str:
    """Wrapper that makes intent explicit when storing private keys."""
    return encrypt(private_key)


def decrypt_private_key(encrypted: str) -> str:
    """Wrapper that makes intent explicit when retrieving private keys."""
    return decrypt(encrypted)
