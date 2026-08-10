from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.stripe_service import InvalidWebhookSignature, apply_event, claim_event_once, verify_and_parse_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify -> deduplicate -> apply, in that order. A forged signature never
    reaches the deduplication step. A replayed real event is acknowledged
    (200) but not re-applied — Stripe should not retry it forever.
    """
    payload = await request.body()

    try:
        event = verify_and_parse_event(payload=payload, sig_header=stripe_signature)
    except InvalidWebhookSignature as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}") from exc

    is_first_delivery = await claim_event_once(db, event=event)
    if is_first_delivery:
        await apply_event(db, event=event)

    await db.commit()
    return {"received": True, "duplicate": not is_first_delivery}
