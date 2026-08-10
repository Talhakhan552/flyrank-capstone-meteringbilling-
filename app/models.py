"""
Data model. Four tables carry the whole system:
  Tenant          — one customer org, isolated by tenant_id everywhere
  Plan            — Free / Pro, with quotas baked in
  UsageEvent      — one row per billable action, deduplicated by idempotency_key
  ProcessedStripeEvent — dedup ledger for incoming webhooks

Money is always stored as integer cents. Never a float, anywhere.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, Enum, ForeignKey, Integer, JSON, String,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class UsageType(str, enum.Enum):
    api_call = "api_call"
    ai_tokens = "ai_tokens"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    incomplete = "incomplete"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "free" | "pro"
    name: Mapped[str] = mapped_column(String, nullable=False)
    api_call_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_token_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    monthly_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_price_id: Mapped[str | None] = mapped_column(String, nullable=True)

    tenants: Mapped[list["Tenant"]] = relationship(back_populates="plan")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), nullable=False, default="free")
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False), nullable=False, default=SubscriptionStatus.active
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped["Plan"] = relationship(back_populates="tenants")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="tenant")


class UsageEvent(Base):
    """
    One billable action. Uniqueness on (tenant_id, idempotency_key) is what
    makes metering exactly-once: a retried request with the same key hits
    the unique constraint instead of inserting a second row.
    """
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    usage_type: Mapped[UsageType] = mapped_column(Enum(UsageType, native_enum=False), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # For ai_tokens events: breakdown used by the pricing engine.
    # {"input": 1000, "cached_input": 200, "output": 500, "reasoning": 100}
    token_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # "YYYY-MM" — the billing period this event rolls up into.
    period: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="usage_events")


class ProcessedStripeEvent(Base):
    """
    Dedup ledger for Stripe webhooks. Stripe may deliver the same event
    more than once (at-least-once delivery) — we process each event id
    exactly once by checking/inserting here before acting on it.
    """
    __tablename__ = "processed_stripe_events"

    stripe_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
