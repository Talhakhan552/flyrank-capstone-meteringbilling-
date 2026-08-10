"""
MeterService — exactly-once usage recording.

The idempotency strategy is deliberately simple and deliberately not a
pre-check: we rely on the database's unique constraint on
(tenant_id, idempotency_key) as the single source of truth, and treat a
constraint violation as "this was already recorded" rather than an error.

Why not "check first, then insert"? Because that has a race: two
concurrent retries can both pass the check before either commits, and
you get two rows anyway. Attempt the insert, let the constraint be the
lock, and fetch the existing row on conflict. This is the same pattern
Stripe's own idempotency-key docs recommend.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageEvent, UsageType


class DuplicateUsageEvent(Exception):
    """Raised internally, then swallowed — signals 'already recorded'."""


def current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def record_usage(
    db: AsyncSession,
    *,
    tenant_id: str,
    usage_type: UsageType,
    quantity: int,
    idempotency_key: str,
    token_breakdown: dict | None = None,
) -> tuple[UsageEvent, bool]:
    """
    Record one usage event exactly once.

    Returns (event, created). created=False means this idempotency_key
    was already used for this tenant — the original event is returned
    unchanged, and the caller must NOT apply quota/cost effects twice.
    """
    event = UsageEvent(
        tenant_id=tenant_id,
        usage_type=usage_type,
        quantity=quantity,
        idempotency_key=idempotency_key,
        token_breakdown=token_breakdown,
        period=current_period(),
    )
    db.add(event)
    try:
        await db.flush()  # triggers the unique constraint without ending the transaction
        return event, True
    except IntegrityError:
        await db.rollback()
        existing = await fetch_existing_event(db, tenant_id, idempotency_key)
        if existing is None:
            # Constraint fired for a reason other than this key (shouldn't
            # happen given the schema) — surface it rather than hiding it.
            raise
        return existing, False


async def fetch_existing_event(db: AsyncSession, tenant_id: str, idempotency_key: str) -> UsageEvent | None:
    result = await db.execute(
        select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def usage_totals_for_period(
    db: AsyncSession, *, tenant_id: str, period: str | None = None
) -> dict[str, int]:
    """Sum quantities per usage_type for the given period (defaults to current month)."""
    period = period or current_period()
    result = await db.execute(
        select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.period == period,
        )
    )
    totals = {UsageType.api_call.value: 0, UsageType.ai_tokens.value: 0}
    for event in result.scalars():
        totals[event.usage_type.value] += event.quantity
    return totals
