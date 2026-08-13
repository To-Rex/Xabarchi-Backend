"""Initial schema: users, api_keys, devices, contacts, templates,
partitioned messages ledger, telegram, notifications, billing.

Revision ID: 0001
Revises:
Create Date: 2026-08-13
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    """created_at/updated_at timestamptz pair used by most tables."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # ------------------------------------------------------------- plans
    plans = op.create_table(
        "plans",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("monthly_price", sa.BigInteger(), nullable=False),
        sa.Column("sms_per_month", sa.Integer(), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=False),
        sa.Column("api_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority_support", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.bulk_insert(
        plans,
        [
            {
                "id": "start",
                "monthly_price": 0,
                "sms_per_month": 500,
                "max_devices": 1,
                "api_access": False,
                "priority_support": False,
            },
            {
                "id": "biznes",
                "monthly_price": 149000,
                "sms_per_month": 10000,
                "max_devices": 5,
                "api_access": True,
                "priority_support": False,
            },
            {
                "id": "korxona",
                "monthly_price": 490000,
                "sms_per_month": 60000,
                "max_devices": 20,
                "api_access": True,
                "priority_support": True,
            },
        ],
    )

    # ------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="owner"),
        sa.Column("avatar_hue", sa.SmallInteger(), nullable=False, server_default="172"),
        sa.Column(
            "plan_id",
            sa.String(16),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
            server_default="start",
        ),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Tashkent"),
        sa.Column("sms_sent_this_month", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # ---------------------------------------------------------- api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # ----------------------------------------------------------- devices
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("operator", sa.String(10), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="offline"),
        sa.Column("connection", sa.String(8), nullable=False, server_default="offline"),
        sa.Column("battery", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("signal", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("android_version", sa.String(8), nullable=False),
        sa.Column("app_version", sa.String(16), nullable=False),
        sa.Column("sent_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_user_deleted", "devices", ["user_id", "deleted_at"])

    # ---------------------------------------------------------- contacts
    op.create_table(
        "contact_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(9), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contact_groups_user_id", "contact_groups", ["user_id"])

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contacts_user_phone", "contacts", ["user_id", "phone"])

    op.create_table(
        "contact_group_members",
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # --------------------------------------------------------- templates
    op.create_table(
        "templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_templates_user_id", "templates", ["user_id"])

    # ---------------------------------------------------------- messages
    # Partitioned, append-only SMS ledger. See app/infrastructure/db/models/message.py.
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("to_phone", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segments", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fail_reason", sa.String(16), nullable=True),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )

    op.execute(
        "COMMENT ON TABLE messages IS "
        "'Append-only SMS ledger partitioned by RANGE (created_at). "
        "New monthly partitions MUST be added ahead of time (cron job or "
        "pg_partman); messages_default catches anything without a partition. "
        "Rows are never deleted — old months are detached/archived.'"
    )

    # Catch-all so an insert never fails if the monthly partition is missing.
    op.execute("CREATE TABLE messages_default PARTITION OF messages DEFAULT")
    # Monthly partitions, 2026-08 .. 2026-12.
    op.execute(
        "CREATE TABLE messages_2026_08 PARTITION OF messages "
        "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')"
    )
    op.execute(
        "CREATE TABLE messages_2026_09 PARTITION OF messages "
        "FOR VALUES FROM ('2026-09-01') TO ('2026-10-01')"
    )
    op.execute(
        "CREATE TABLE messages_2026_10 PARTITION OF messages "
        "FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')"
    )
    op.execute(
        "CREATE TABLE messages_2026_11 PARTITION OF messages "
        "FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')"
    )
    op.execute(
        "CREATE TABLE messages_2026_12 PARTITION OF messages "
        "FOR VALUES FROM ('2026-12-01') TO ('2027-01-01')"
    )

    # Partitioned indexes on the parent — propagate to every partition.
    op.create_index("ix_messages_user_created", "messages", ["user_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_messages_queue",
        "messages",
        ["device_id", "priority", "created_at"],
        postgresql_where=sa.text("status IN ('queued', 'sending')"),
    )
    op.create_index("ix_messages_status", "messages", ["status"])

    # Aggregated per-user daily send stats (frontend DailyStat contract).
    op.execute(
        """
        CREATE VIEW daily_stats AS
        SELECT
            user_id,
            date_trunc('day', created_at)::date AS date,
            count(*) FILTER (WHERE status IN ('sent', 'delivered')) AS sent,
            count(*) FILTER (WHERE status = 'delivered') AS delivered,
            count(*) FILTER (WHERE status = 'failed') AS failed
        FROM messages
        GROUP BY 1, 2
        """
    )

    # ---------------------------------------------------------- telegram
    op.create_table(
        "telegram_bots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="active"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("webhook_ok", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # One live bot per user; soft-deleted rows don't block reconnecting.
    op.create_index(
        "uq_telegram_bots_user_live",
        "telegram_bots",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "bot_subscribers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("telegram_bots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("avatar_hue", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bot_subscribers_bot_id", "bot_subscribers", ["bot_id"])

    op.create_table(
        "bot_broadcasts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("telegram_bots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("media_name", sa.String(255), nullable=True),
        sa.Column("button_label", sa.String(64), nullable=True),
        sa.Column("button_url", sa.String(2048), nullable=True),
        sa.Column("audience", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_bot_broadcasts_bot_created", "bot_broadcasts", ["bot_id", sa.text("created_at DESC")])

    # ----------------------------------------------------- notifications
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("title", postgresql.JSONB(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
    )
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "read", sa.text("created_at DESC")],
    )

    # ---------------------------------------------------------- invoices
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column(
            "plan_id",
            sa.String(16),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period", sa.String(32), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("notifications")
    op.drop_table("bot_broadcasts")
    op.drop_table("bot_subscribers")
    op.drop_table("telegram_bots")
    op.execute("DROP VIEW IF EXISTS daily_stats")
    # Dropping the partitioned parent drops all attached partitions.
    op.drop_table("messages")
    op.drop_table("templates")
    op.drop_table("contact_group_members")
    op.drop_table("contacts")
    op.drop_table("contact_groups")
    op.drop_table("devices")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("plans")
