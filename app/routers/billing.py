from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_tenant
from app.models import Tenant
from app.schemas import CheckoutRequest, CheckoutResponse
from app.services.stripe_service import create_checkout_session

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe test-mode Checkout Session for a tenant upgrading to Pro."""
    price_id = body.price_id or settings.stripe_price_id_pro
    session = create_checkout_session(tenant=tenant, price_id=price_id)
    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


@router.get("/success")
async def success(session_id: str | None = None):
    return {"status": "ok", "session_id": session_id, "message": "Checkout complete — webhook will sync your plan."}


@router.get("/cancel")
async def cancel():
    return {"status": "canceled"}
