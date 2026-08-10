"""
The metering + quota + rollup surface. This is the only router that
touches usage_events directly — HTTP concerns stop here, business logic
lives in app/services/.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant, get_tenant_plan
from app.models import Tenant, UsageType
from app.schemas import GenerateRequest, GenerateResponse, UsageResponse
from app.services import metering, pricing
from app.services.quota import check_quota

router = APIRouter(tags=["usage"])


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    A stand-in for any billable action (e.g. an AI generation call).
    Flow: check quota -> record usage (idempotent) -> price this event.

    Quota is checked BEFORE recording. If the request is a retry (same
    Idempotency-Key), the earlier recorded event is returned as-is and
    quota is not re-checked or re-applied — a replay must be a no-op,
    not a second deduction.
    """
    plan = await get_tenant_plan(tenant, db)
    usage_type = UsageType(body.usage_type)

    # Fast path: if this idempotency key was already used, short-circuit
    # before touching quota at all — replays must be side-effect free.
    existing = await metering.fetch_existing_event(db, tenant.id, idempotency_key)
    if existing is not None:
        cost = _price_event(existing)
        return GenerateResponse(
            usage_event_id=existing.id,
            tenant_id=tenant.id,
            usage_type=existing.usage_type.value,
            quantity=existing.quantity,
            idempotent_replay=True,
            cost_cents_for_this_event=cost,
        )

    decision = await check_quota(db, tenant=tenant, plan=plan, usage_type=usage_type, requested_qty=body.quantity)
    if not decision.allowed:
        raise HTTPException(status_code=decision.status_code, detail=decision.reason)

    token_breakdown = body.token_breakdown.model_dump() if body.token_breakdown else None
    event, created = await metering.record_usage(
        db,
        tenant_id=tenant.id,
        usage_type=usage_type,
        quantity=body.quantity,
        idempotency_key=idempotency_key,
        token_breakdown=token_breakdown,
    )
    await db.commit()

    cost = _price_event(event)
    return GenerateResponse(
        usage_event_id=event.id,
        tenant_id=tenant.id,
        usage_type=event.usage_type.value,
        quantity=event.quantity,
        idempotent_replay=not created,
        cost_cents_for_this_event=cost,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    plan = await get_tenant_plan(tenant, db)
    totals = await metering.usage_totals_for_period(db, tenant_id=tenant.id)

    events = await _tenant_period_events(db, tenant.id)
    cost_cents = sum(_price_event(e) for e in events)

    return UsageResponse(
        tenant_id=tenant.id,
        plan=plan.id,
        period=metering.current_period(),
        api_calls_used=totals[UsageType.api_call.value],
        api_calls_limit=plan.api_call_limit,
        ai_tokens_used=totals[UsageType.ai_tokens.value],
        ai_tokens_limit=plan.ai_token_limit,
        cost_cents=cost_cents,
    )


def _price_event(event) -> int:
    if event.usage_type == UsageType.api_call:
        return pricing.calculate_api_call_cost_cents(event.quantity)
    breakdown = event.token_breakdown or {}
    return pricing.calculate_token_cost_cents(
        input_tokens=breakdown.get("input", 0),
        cached_input_tokens=breakdown.get("cached_input", 0),
        output_tokens=breakdown.get("output", 0),
        reasoning_tokens=breakdown.get("reasoning", 0),
    )


async def _tenant_period_events(db: AsyncSession, tenant_id: str):
    from sqlalchemy import select

    from app.models import UsageEvent

    period = metering.current_period()
    result = await db.execute(
        select(UsageEvent).where(UsageEvent.tenant_id == tenant_id, UsageEvent.period == period)
    )
    return list(result.scalars())
