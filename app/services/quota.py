"""
QuotaService — decide whether a billable action is allowed before it
happens (metering records what happened; this decides what's allowed to).

Two distinct failure modes, two distinct status codes:

  429 Too Many Requests  — the tenant is in good standing but has used
                            up their plan's monthly allowance.
  402 Payment Required   — the tenant's subscription itself is not in a
                            payable state (past_due / canceled /
                            incomplete): no amount of quota headroom
                            fixes this, they need to fix billing first.

Boundary rule (explicit, tested, and explainable at demo):
the Nth call that would make usage EXCEED the limit is rejected. A
tenant whose current usage is exactly at the limit and requests one
more unit is rejected; a request that lands exactly ON the limit is
allowed. i.e. `current + requested > limit` is the rejection condition.
"""
from dataclasses import dataclass

from app.models import Plan, SubscriptionStatus, Tenant, UsageType
from app.services.metering import usage_totals_for_period

UNPAYABLE_STATUSES = {SubscriptionStatus.past_due, SubscriptionStatus.canceled, SubscriptionStatus.incomplete}


@dataclass
class QuotaDecision:
    allowed: bool
    status_code: int | None = None
    reason: str | None = None
    used: int = 0
    limit: int = 0


async def check_quota(db, *, tenant: Tenant, plan: Plan, usage_type: UsageType, requested_qty: int) -> QuotaDecision:
    if tenant.subscription_status in UNPAYABLE_STATUSES:
        return QuotaDecision(
            allowed=False,
            status_code=402,
            reason=(
                f"Subscription status is '{tenant.subscription_status.value}'. "
                "Update your payment method to restore access."
            ),
        )

    totals = await usage_totals_for_period(db, tenant_id=tenant.id)
    limit = plan.api_call_limit if usage_type == UsageType.api_call else plan.ai_token_limit
    used = totals[usage_type.value]

    if used + requested_qty > limit:
        return QuotaDecision(
            allowed=False,
            status_code=429,
            reason=(
                f"Monthly {usage_type.value} quota exceeded: {used}/{limit} used, "
                f"{requested_qty} requested. Upgrade your plan or wait for next cycle."
            ),
            used=used,
            limit=limit,
        )

    return QuotaDecision(allowed=True, used=used, limit=limit)
