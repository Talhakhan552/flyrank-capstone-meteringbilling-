"""
Stripe integration (test mode only). Two directions of truth:

  Outbound: create a Checkout Session so a tenant can subscribe to Pro.
  Inbound:  verify + deduplicate + apply webhook events that tell us what
            actually happened. Payment truth lives at Stripe — this
            service only ever mirrors verified events into our database,
            never guesses ahead of them.
"""
import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ProcessedStripeEvent, SubscriptionStatus, Tenant

stripe.api_key = settings.stripe_secret_key


class InvalidWebhookSignature(Exception):
    pass


def create_checkout_session(*, tenant: Tenant, price_id: str) -> stripe.checkout.Session:
    """Create a test-mode Checkout Session for a tenant upgrading to Pro."""
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=tenant.stripe_customer_id,  # None is fine — Stripe creates one
        client_reference_id=tenant.id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.stripe_success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=settings.stripe_cancel_url,
    )
    return session


def verify_and_parse_event(*, payload: bytes, sig_header: str) -> stripe.Event:
    """
    Verify the webhook signature against STRIPE_WEBHOOK_SECRET. A forged
    or malformed payload raises InvalidWebhookSignature — the router
    turns that into a 400 with nothing else touched.
    """
    try:
        return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise InvalidWebhookSignature(str(exc)) from exc


async def claim_event_once(db: AsyncSession, *, event: stripe.Event) -> bool:
    """
    Insert a dedup row for this Stripe event id. Returns True if this is
    the first time we've seen it (proceed), False if it's a replay
    (already processed — do nothing further, but still ack 200).
    """
    marker = ProcessedStripeEvent(stripe_event_id=event["id"], event_type=event["type"])
    db.add(marker)
    try:
        await db.flush()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def apply_event(db: AsyncSession, *, event: stripe.Event) -> None:
    """Mirror a verified, first-seen Stripe event into our tenant record."""
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        tenant_id = data.get("client_reference_id")
        tenant = await _get_tenant(db, tenant_id)
        if tenant is None:
            return
        tenant.stripe_customer_id = data.get("customer") or tenant.stripe_customer_id
        tenant.stripe_subscription_id = data.get("subscription") or tenant.stripe_subscription_id
        tenant.plan_id = "pro"
        tenant.subscription_status = SubscriptionStatus.active

    elif event_type == "customer.subscription.updated":
        tenant = await _get_tenant_by_subscription(db, data.get("id"))
        if tenant is None:
            return
        tenant.subscription_status = _map_stripe_status(data.get("status"))

    elif event_type == "customer.subscription.deleted":
        tenant = await _get_tenant_by_subscription(db, data.get("id"))
        if tenant is None:
            return
        tenant.plan_id = "free"
        tenant.subscription_status = SubscriptionStatus.canceled
        tenant.stripe_subscription_id = None


def _map_stripe_status(stripe_status: str | None) -> SubscriptionStatus:
    mapping = {
        "active": SubscriptionStatus.active,
        "trialing": SubscriptionStatus.active,
        "past_due": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "unpaid": SubscriptionStatus.past_due,
        "incomplete": SubscriptionStatus.incomplete,
        "incomplete_expired": SubscriptionStatus.canceled,
    }
    return mapping.get(stripe_status or "", SubscriptionStatus.incomplete)


async def _get_tenant(db: AsyncSession, tenant_id: str | None) -> Tenant | None:
    if not tenant_id:
        return None
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def _get_tenant_by_subscription(db: AsyncSession, subscription_id: str | None) -> Tenant | None:
    if not subscription_id:
        return None
    result = await db.execute(select(Tenant).where(Tenant.stripe_subscription_id == subscription_id))
    return result.scalar_one_or_none()
