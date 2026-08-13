"""Real Telegram sending: encrypted token, webhook secret, subscriber chat_id.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("telegram_bots", sa.Column("token_enc", sa.Text(), nullable=True))
    op.add_column("telegram_bots", sa.Column("bot_user_id", sa.BigInteger(), nullable=True))
    op.add_column("telegram_bots", sa.Column("webhook_secret", sa.String(48), nullable=True))
    op.create_index(
        "ix_telegram_bots_webhook_secret", "telegram_bots", ["webhook_secret"]
    )

    op.add_column("bot_subscribers", sa.Column("chat_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_bot_subscribers_chat_id", "bot_subscribers", ["chat_id"])
    # One live subscriber row per (bot, chat); soft-deleted rows don't block rejoin.
    op.create_index(
        "uq_bot_subscribers_bot_chat_live",
        "bot_subscribers",
        ["bot_id", "chat_id"],
        unique=True,
        postgresql_where=sa.text("chat_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bot_subscribers_bot_chat_live", table_name="bot_subscribers")
    op.drop_index("ix_bot_subscribers_chat_id", table_name="bot_subscribers")
    op.drop_column("bot_subscribers", "chat_id")
    op.drop_index("ix_telegram_bots_webhook_secret", table_name="telegram_bots")
    op.drop_column("telegram_bots", "webhook_secret")
    op.drop_column("telegram_bots", "bot_user_id")
    op.drop_column("telegram_bots", "token_enc")
