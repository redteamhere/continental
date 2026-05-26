"""Extend Currency and Chain enums with new payment methods

Adds: ETH, BNB, LTC, DOGE, TRX, TON, USDT_TON, FTM to currency enum
Adds: BSC, DOGECOIN, FANTOM, TON to chain enum
Also backfills USDT_BEP20, USDT_ERC20 that were missing from the initial migration.

Revision ID: 003
Revises: 002
Create Date: 2026-05-26
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Currency enum — add all missing/new values ──────────────────────────
    # Use IF NOT EXISTS so this migration is safe to re-run
    for val in (
        "USDT_BEP20",  # may already exist — safe with IF NOT EXISTS
        "USDT_ERC20",  # same
        "USDT_TON",
        "ETH",
        "BNB",
        "LTC",
        "DOGE",
        "TRX",
        "TON",
        "FTM",
    ):
        op.execute(f"ALTER TYPE currency ADD VALUE IF NOT EXISTS '{val}'")

    # ── Chain enum — add new chains ─────────────────────────────────────────
    for val in (
        "BSC",       # may already exist — safe with IF NOT EXISTS
        "DOGECOIN",
        "FANTOM",
        "TON",
    ):
        op.execute(f"ALTER TYPE chain ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    # PostgreSQL does not support DROP VALUE on enums.
    # A full downgrade would require recreating the enum without the new values
    # and casting the column — skip for safety in production.
    pass
