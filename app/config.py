from __future__ import annotations

import secrets
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Bot ──────────────────────────────────────────────────
    BOT_TOKEN: str
    BOT_WEBHOOK_URL: str = ""
    BOT_WEBHOOK_PATH: str = "/webhook"
    BOT_WEBHOOK_SECRET: str = secrets.token_hex(16)

    # ── Admin ────────────────────────────────────────────────
    ADMIN_IDS: List[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, int):
            return [v]
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json
                return [int(x) for x in json.loads(v)]
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return []

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/escrow_bot"

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Security ─────────────────────────────────────────────
    SECRET_KEY: str = secrets.token_hex(32)
    ENCRYPTION_KEY: str = secrets.token_hex(32)  # 32-byte AES-256 key

    # ── Fees ─────────────────────────────────────────────────
    ESCROW_FEE_PERCENT: float = 1.5
    MIN_DEAL_AMOUNT_USD: float = 10.0
    MAX_DEAL_AMOUNT_USD: float = 100_000.0

    # ── Admin cold wallets ───────────────────────────────────
    # Set in Railway. Buyer sends here; admin confirms via /confirm_payment DEAL-XXXXX
    COLD_WALLET_USDT_TRC20: str = ""
    COLD_WALLET_USDT_BEP20: str = ""
    COLD_WALLET_USDT_ERC20: str = ""
    COLD_WALLET_BTC:        str = ""

    # ── Tron / USDT TRC20 ────────────────────────────────────
    TRON_API_KEY: str = ""
    USDT_TRC20_CONFIRMATIONS: int = 6

    # ── Deal Defaults ────────────────────────────────────────
    DEFAULT_DEAL_DEADLINE_DAYS: int = 7
    MAX_DEAL_DEADLINE_DAYS: int = 30
    DEAL_EXPIRY_WARNING_HOURS: int = 24

    # ── Rate Limiting ────────────────────────────────────────
    MAX_REQUESTS_PER_MINUTE: int = 30
    MAX_DEALS_PER_DAY: int = 10

    # ── Referral ─────────────────────────────────────────────
    REFERRAL_BONUS_PERCENT: float = 0.1

    # ── HD Wallet master seed ────────────────────────────────
    MASTER_MNEMONIC: str = ""

    # ── Telegram MTProto (for deal group creation via Telethon) ─────────────
    TELEGRAM_API_ID: int = 0       # from https://my.telegram.org/apps
    TELEGRAM_API_HASH: str = ""    # from https://my.telegram.org/apps

    # ── Web App (Telegram Mini App) ──────────────────────────
    WEB_APP_URL: str = ""   # e.g. https://yourname.github.io/continental/webapp/pin.html

    # ── App ──────────────────────────────────────────────────
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOCAL_DEV: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def confirmations_for(self) -> dict[str, int]:
        return {
            "USDT_TRC20": self.USDT_TRC20_CONFIRMATIONS,
            "BTC": self.BTC_CONFIRMATIONS,
            "ETH": self.ETH_CONFIRMATIONS,
            "LTC": self.LTC_CONFIRMATIONS,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
