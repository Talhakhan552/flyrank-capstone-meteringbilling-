"""
Tenant resolution. Every billable/read endpoint requires an
`X-Tenant-Id` header — this is the multi-tenant isolation boundary: no
query in this codebase should ever run without a tenant_id filter, and
this dependency is where that id enters the request.

(A real product would resolve tenant from an API key or JWT. Swapping
that in later only touches this one function — the rest of the app
never changes. That's the point of the layering.)
"""
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.models import Plan, Tenant


async def get_current_tenant(
    x_tenant_id: str = Header(..., description="Tenant identifier"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == x_tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant: {x_tenant_id}")
    return tenant


async def get_tenant_plan(tenant: Tenant, db: AsyncSession) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == tenant.plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=500, detail=f"Tenant plan '{tenant.plan_id}' not found")
    return plan
