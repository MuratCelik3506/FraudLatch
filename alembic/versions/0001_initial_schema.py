"""Create the core transaction and processing tables."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column("customer_id", sa.String(length=128), nullable=False),
        sa.Column("merchant_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("source_step", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.create_index(
        "ix_transactions_customer_event_time", "transactions", ["customer_id", "event_time"]
    )
    op.create_index(
        "ix_transactions_merchant_event_time", "transactions", ["merchant_id", "event_time"]
    )
    op.create_table(
        "risk_assessments",
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("engine_version", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')", name="ck_risk_status"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["transactions.transaction_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.create_table(
        "processing_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["transactions.transaction_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_processing_events_transaction_created",
        "processing_events",
        ["transaction_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_events_transaction_created", table_name="processing_events")
    op.drop_table("processing_events")
    op.drop_table("risk_assessments")
    op.drop_index("ix_transactions_merchant_event_time", table_name="transactions")
    op.drop_index("ix_transactions_customer_event_time", table_name="transactions")
    op.drop_table("transactions")
