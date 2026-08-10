"""
Seed script: two plans + two demo tenants.
  demo-free    — Free plan, seeded near its API-call quota (995/1000) so
                 the boundary is one curl away from the demo.
  demo-pro     — Pro plan, fresh, for the checkout/webhook demo path.

Run: python -m scripts.seed
"""
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, engine
from app.models import Plan, SubscriptionStatus, Tenant, UsageEvent, UsageType
from app.services.metering import current_period


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        plans = {
            "free": Plan(id="free", name="Free", api_call_limit=1000, ai_token_limit=100_000, monthly_price_cents=0),
            "pro": Plan(
                id="pro",
                name="Pro",
                api_call_limit=50_000,
                ai_token_limit=5_000_000,
                monthly_price_cents=2900,
                stripe_price_id="price_placeholder",
            ),
        }
        for plan in plans.values():
            existing = await db.execute(select(Plan).where(Plan.id == plan.id))
            if existing.scalar_one_or_none() is None:
                db.add(plan)
        await db.flush()

        tenants = [
            Tenant(id="demo-free", name="Demo Free Tenant", plan_id="free", subscription_status=SubscriptionStatus.active),
            Tenant(id="demo-pro", name="Demo Pro Tenant", plan_id="free", subscription_status=SubscriptionStatus.active),
        ]
        for tenant in tenants:
            existing = await db.execute(select(Tenant).where(Tenant.id == tenant.id))
            if existing.scalar_one_or_none() is None:
                db.add(tenant)
        await db.flush()

        # Seed demo-free to 995/1000 API calls so the boundary is 5 requests away.
        existing_event = await db.execute(
            select(UsageEvent).where(UsageEvent.tenant_id == "demo-free", UsageEvent.idempotency_key == "seed-bulk")
        )
        if existing_event.scalar_one_or_none() is None:
            db.add(
                UsageEvent(
                    tenant_id="demo-free",
                    usage_type=UsageType.api_call,
                    quantity=995,
                    idempotency_key="seed-bulk",
                    period=current_period(),
                )
            )

        await db.commit()
        print("Seed complete: plans=[free, pro], tenants=[demo-free @ 995/1000 calls, demo-pro @ 0]")


if __name__ == "__main__":
    asyncio.run(seed())
