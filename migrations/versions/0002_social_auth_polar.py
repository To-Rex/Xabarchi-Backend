"""Social auth (oauth_accounts, nullable password) + e-mail verification
+ Polar billing columns (polar_customer_id, invoices.external_id).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Social-only accounts have no password.
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("polar_customer_id", sa.String(64), nullable=True))
    op.create_index("ix_users_polar_customer_id", "users", ["polar_customer_id"])

    op.create_table(
        "oauth_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_index(
        "uq_oauth_provider_subject", "oauth_accounts", ["provider", "subject"], unique=True
    )

    # Polar order id — webhook idempotency key.
    op.add_column("invoices", sa.Column("external_id", sa.String(64), nullable=True))
    op.create_index("uq_invoices_external_id", "invoices", ["external_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_invoices_external_id", table_name="invoices")
    op.drop_column("invoices", "external_id")
    op.drop_index("uq_oauth_provider_subject", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
    op.drop_index("ix_users_polar_customer_id", table_name="users")
    op.drop_column("users", "polar_customer_id")
    op.drop_column("users", "email_verified_at")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
