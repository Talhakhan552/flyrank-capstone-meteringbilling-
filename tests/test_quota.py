import pytest

from app.models import UsageType
from app.services import metering


async def _bulk_seed(db_session, tenant_id: str, quantity: int):
    await metering.record_usage(
        db_session,
        tenant_id=tenant_id,
        usage_type=UsageType.api_call,
        quantity=quantity,
        idempotency_key="bulk-seed",
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_request_that_lands_exactly_on_limit_is_allowed(client, tenant_headers, db_session):
    # Free plan limit = 1000. Seed 999, then request 1 more -> lands exactly at 1000 -> allowed.
    await _bulk_seed(db_session, "t-free", 999)

    resp = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-free", "boundary-key"),
    )
    assert resp.status_code == 200

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["api_calls_used"] == 1000


@pytest.mark.asyncio
async def test_request_that_would_exceed_limit_is_rejected_429(client, tenant_headers, db_session):
    # Seed exactly to the limit. The next single-unit request must be rejected.
    await _bulk_seed(db_session, "t-free", 1000)

    resp = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-free", "over-key"),
    )
    assert resp.status_code == 429
    assert "quota exceeded" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_request_just_under_limit_is_allowed(client, tenant_headers, db_session):
    await _bulk_seed(db_session, "t-free", 998)

    resp = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-free", "under-key"),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_a_single_large_request_that_would_overshoot_is_rejected(client, tenant_headers, db_session):
    # 950 used, requesting 100 more would land at 1050 > 1000 -> rejected outright,
    # not partially fulfilled.
    await _bulk_seed(db_session, "t-free", 950)

    resp = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 100},
        headers=tenant_headers("t-free", "overshoot-key"),
    )
    assert resp.status_code == 429

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["api_calls_used"] == 950  # unchanged — rejected requests record nothing


@pytest.mark.asyncio
async def test_past_due_subscription_gets_402_regardless_of_quota(client, tenant_headers):
    # t-pastdue is on Pro (huge limit) but its subscription is past_due.
    resp = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-pastdue", "pastdue-key"),
    )
    assert resp.status_code == 402
    assert "past_due" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_after_rejection_still_fails_until_capacity_frees(client, tenant_headers, db_session):
    await _bulk_seed(db_session, "t-free", 1000)

    first = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-free", "retry-after-429"),
    )
    assert first.status_code == 429

    # Retrying the exact same request (same idempotency key) also fails —
    # a rejected request was never recorded, so there's nothing to replay.
    second = await client.post(
        "/generate",
        json={"usage_type": "api_call", "quantity": 1},
        headers=tenant_headers("t-free", "retry-after-429"),
    )
    assert second.status_code == 429
