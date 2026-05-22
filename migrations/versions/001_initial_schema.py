"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("username", sa.String(64), unique=True, nullable=True),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("pin_hash", sa.String(256), nullable=True),
        sa.Column("pin_attempts", sa.Integer(), default=0, nullable=False),
        sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role", sa.Enum("user", "moderator", "admin", name="userrole"), default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_banned", sa.Boolean(), default=False, nullable=False),
        sa.Column("ban_reason", sa.String(512), nullable=True),
        sa.Column("referral_code", sa.String(16), unique=True, nullable=False),
        sa.Column("referred_by_id", sa.Integer(), nullable=True),
        sa.Column("reputation_score", sa.Float(), default=5.0, nullable=False),
        sa.Column("total_deals", sa.Integer(), default=0, nullable=False),
        sa.Column("total_purchases", sa.Integer(), default=0, nullable=False),
        sa.Column("total_sales", sa.Integer(), default=0, nullable=False),
        sa.Column("total_disputes_opened", sa.Integer(), default=0, nullable=False),
        sa.Column("total_disputes_won", sa.Integer(), default=0, nullable=False),
        sa.Column("kyc_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("language_code", sa.String(8), default="en", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])

    # Wallets (before deals — deals reference wallets)
    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Integer(), nullable=True),
        sa.Column("chain", sa.Enum("TRON", "ETHEREUM", "BITCOIN", "LITECOIN", name="chain"), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("derivation_path", sa.String(64), nullable=True),
        sa.Column("hd_index", sa.Integer(), nullable=True),
        sa.Column("expected_amount", sa.Numeric(28, 8), nullable=True),
        sa.Column("confirmed_balance", sa.Numeric(28, 8), default=0, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_swept", sa.Boolean(), default=False, nullable=False),
        sa.Column("swept_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sweep_tx_hash", sa.String(128), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_count", sa.Integer(), default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wallets_address", "wallets", ["address"])

    # Deals
    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_number", sa.String(32), unique=True, nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("currency", sa.Enum("USDT_TRC20", "BTC", "ETH", "LTC", name="currency"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 2), nullable=True),
        sa.Column("fee_amount", sa.Numeric(28, 8), default=0, nullable=False),
        sa.Column("fee_paid", sa.Boolean(), default=False, nullable=False),
        sa.Column("status", sa.Enum(
            "pending", "awaiting_payment", "funded", "in_progress",
            "completed", "cancelled", "disputed", "refunded", name="dealstatus"
        ), default="pending", nullable=False),
        sa.Column("escrow_wallet_id", sa.Integer(), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("seller_accepted", sa.Boolean(), default=False, nullable=False),
        sa.Column("buyer_confirmed_completion", sa.Boolean(), default=False, nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_warning_sent", sa.Boolean(), default=False, nullable=False),
        sa.Column("cancellation_reason", sa.String(512), nullable=True),
        sa.Column("cancelled_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("funded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_deals_deal_number", "deals", ["deal_number"])
    op.create_index("ix_deals_buyer_id", "deals", ["buyer_id"])
    op.create_index("ix_deals_seller_id", "deals", ["seller_id"])
    op.create_index("ix_deals_status", "deals", ["status"])

    # Add FK from wallets to deals
    op.create_foreign_key("fk_wallets_deal_id", "wallets", "deals", ["deal_id"], ["id"])

    # Transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id"), nullable=False),
        sa.Column("wallet_id", sa.Integer(), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("tx_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("from_address", sa.String(128), nullable=True),
        sa.Column("to_address", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("confirmations", sa.Integer(), default=0, nullable=False),
        sa.Column("required_confirmations", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "confirming", "confirmed", "failed", "duplicate", name="txstatus"), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=True),
        sa.Column("block_hash", sa.String(128), nullable=True),
        sa.Column("gas_used", sa.Integer(), nullable=True),
        sa.Column("fee_amount", sa.Numeric(28, 18), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactions_tx_hash", "transactions", ["tx_hash"])

    # Disputes
    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id"), unique=True, nullable=False),
        sa.Column("opened_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.Enum("open", "under_review", "resolved", "closed", name="disputestatus"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_file_ids", JSON, nullable=True),
        sa.Column("resolution_type", sa.Enum("buyer_refund", "seller_release", "partial_split", "no_action", name="resolutiontype"), nullable=True),
        sa.Column("buyer_split_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("seller_split_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id"), unique=True, nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Audit logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details", JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), default=False, nullable=False),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("deals.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("audit_logs")
    op.drop_table("reviews")
    op.drop_table("disputes")
    op.drop_table("transactions")
    op.drop_constraint("fk_wallets_deal_id", "wallets", type_="foreignkey")
    op.drop_table("deals")
    op.drop_table("wallets")
    op.drop_table("users")
    # Drop enums
    for enum_name in ["userrole", "chain", "currency", "dealstatus", "txstatus", "disputestatus", "resolutiontype"]:
        sa.Enum(name=enum_name).drop(op.get_bind())
