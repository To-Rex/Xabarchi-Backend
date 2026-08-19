"""Scheduled SMS: messages.scheduled_at + a due-scheduled index.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The reaper scans for scheduled messages whose time has come.
    op.create_index(
        "ix_messages_scheduled_due",
        "messages",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_scheduled_due", table_name="messages")
    op.drop_column("messages", "scheduled_at")
