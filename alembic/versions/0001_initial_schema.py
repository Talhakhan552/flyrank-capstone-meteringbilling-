"""initial schema: plans, tenants, usage_events, processed_stripe_events

Revision ID: 0001
Revises:
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("api_call_limit", sa.Integer(), nullable=False),
        sa.Column("ai_token_limit", sa.BigInteger(), nullable=False),
        sa.Column("monthly_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stripe_price_id", sa.String(), nullable=True),
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), sa.ForeignKey("plans.id"), nullable=False, server_default="free"),
        sa.Column("subscription_status", sa.String(), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(), nullable=True, unique=True),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("usage_type", sa.String(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False, index=True),
        sa.Column("token_breakdown", sa.JSON(), nullable=True),
        sa.Column("period", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency_key"),
    )

    op.create_table(
        "processed_stripe_events",
        sa.Column("stripe_event_id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("processed_stripe_events")
    op.drop_table("usage_events")
    op.drop_table("tenants")
    op.drop_table("plans")
