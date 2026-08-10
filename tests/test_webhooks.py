"""
Probe 3: a completed Checkout webhook flips a tenant Free -> Pro.
Probe 4: a forged signature is rejected (400, nothing changes); a
         replayed real event is processed exactly once.
"""
import hashlib
import hmac
import json
import time

import pytest

from app.config import settings


def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a valid Stripe-Signature header the way Stripe itself does."""
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _checkout_completed_payload(tenant_id: str, event_id: str = "evt_test_1") -> bytes:
    body = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": tenant_id,
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
            }
        },
    }
    return json.dumps(body).encode()


@pytest.mark.asyncio
async def test_forged_signature_is_rejected_and_nothing_changes(client):
    payload = _checkout_completed_payload("t-free")
    bad_header = "t=1111111111,v1=deadbeef" * 2

    resp = await client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": bad_header, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["plan"] == "free"  # unchanged


@pytest.mark.asyncio
async def test_valid_checkout_completed_webhook_flips_tenant_to_pro(client):
    payload = _checkout_completed_payload("t-free", event_id="evt_checkout_1")
    header = _sign(payload, settings.stripe_webhook_secret)

    resp = await client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "duplicate": False}

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    body = usage.json()
    assert body["plan"] == "pro"
    assert body["api_calls_limit"] == 50_000  # Pro limit, not Free


@pytest.mark.asyncio
async def test_replayed_real_event_is_processed_exactly_once(client):
    payload = _checkout_completed_payload("t-free", event_id="evt_replay_1")
    header = _sign(payload, settings.stripe_webhook_secret)

    first = await client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    second = await client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )

    assert first.status_code == 200 and first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True

    # Still just one plan flip's worth of state — no double application.
    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["plan"] == "pro"


@pytest.mark.asyncio
async def test_subscription_deleted_reverts_tenant_to_free(client):
    # First, get t-pro-like state via checkout, then cancel it.
    checkout_payload = _checkout_completed_payload("t-free", event_id="evt_checkout_2")
    await client.post(
        "/webhooks/stripe",
        content=checkout_payload,
        headers={"Stripe-Signature": _sign(checkout_payload, settings.stripe_webhook_secret), "Content-Type": "application/json"},
    )

    deleted_body = {
        "id": "evt_sub_deleted_1",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_test_123"}},
    }
    deleted_payload = json.dumps(deleted_body).encode()
    resp = await client.post(
        "/webhooks/stripe",
        content=deleted_payload,
        headers={"Stripe-Signature": _sign(deleted_payload, settings.stripe_webhook_secret), "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["plan"] == "free"
