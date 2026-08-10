"""
Definition of Done: "A billable action creates exactly one usage event,
even under retries — deduplicated by idempotency key. A test proves
double-counting cannot happen." This is that test.
"""
import pytest


@pytest.mark.asyncio
async def test_same_idempotency_key_creates_one_usage_event(client, tenant_headers, db_session):
    headers = tenant_headers("t-free", idempotency_key="retry-key-abc")
    payload = {"usage_type": "api_call", "quantity": 1}

    first = await client.post("/generate", json=payload, headers=headers)
    second = await client.post("/generate", json=payload, headers=headers)
    third = await client.post("/generate", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200

    first_body, second_body, third_body = first.json(), second.json(), third.json()

    # Same event id every time — proof it's the same underlying row.
    assert first_body["usage_event_id"] == second_body["usage_event_id"] == third_body["usage_event_id"]
    assert first_body["idempotent_replay"] is False
    assert second_body["idempotent_replay"] is True
    assert third_body["idempotent_replay"] is True

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["api_calls_used"] == 1  # NOT 3


@pytest.mark.asyncio
async def test_different_idempotency_keys_create_separate_events(client, tenant_headers):
    payload = {"usage_type": "api_call", "quantity": 1}

    r1 = await client.post("/generate", json=payload, headers=tenant_headers("t-free", "key-a"))
    r2 = await client.post("/generate", json=payload, headers=tenant_headers("t-free", "key-b"))

    assert r1.json()["usage_event_id"] != r2.json()["usage_event_id"]

    usage = await client.get("/usage", headers={"X-Tenant-Id": "t-free"})
    assert usage.json()["api_calls_used"] == 2


@pytest.mark.asyncio
async def test_same_idempotency_key_different_tenants_are_independent(client, tenant_headers):
    payload = {"usage_type": "api_call", "quantity": 1}

    r1 = await client.post("/generate", json=payload, headers=tenant_headers("t-free", "shared-key"))
    r2 = await client.post("/generate", json=payload, headers=tenant_headers("t-pro", "shared-key"))

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["usage_event_id"] != r2.json()["usage_event_id"]
