"""Add deal chat group columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-23
"""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("chat_group_id", sa.BigInteger(), nullable=True))
    op.add_column("deals", sa.Column("chat_invite_link", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "chat_invite_link")
    op.drop_column("deals", "chat_group_id")
