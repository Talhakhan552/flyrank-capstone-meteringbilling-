# Evidence — Definition of Done

One pasted proof per checkbox from the capstone brief §6. Automated
test suite output at the bottom, plus live verification against real
Stripe test-mode infrastructure (not just self-signed test fixtures).

## Metering

**A billable action creates exactly one usage event, even under retries.**
```
tests/test_idempotency.py::test_same_idempotency_key_creates_one_usage_event PASSED
```
Same `Idempotency-Key` sent 3 times → `usage_event_id` identical all
three times; `/usage` shows `api_calls_used == 1`, not 3.

**A test proves double-counting cannot happen.**
```
tests/test_idempotency.py::test_different_idempotency_keys_create_separate_events PASSED
tests/test_idempotency.py::test_same_idempotency_key_different_tenants_are_independent PASSED
```
The uniqueness is scoped to `(tenant_id, idempotency_key)` — verified
both that distinct keys create distinct events, and that the same key
reused across tenants does not collide.

## Quotas

**Usage is checked against the tenant's plan; requests over the limit are rejected.**
```
tests/test_quota.py::test_a_single_large_request_that_would_overshoot_is_rejected PASSED
```
950/1000 used; a single request for 100 more (would land at 1050) is
rejected outright with 429, and `/usage` still shows 950 used —
nothing partially applied.

**Responses carry the correct status codes (429/402) and a message explaining why.**
```
tests/test_quota.py::test_request_that_lands_exactly_on_limit_is_allowed PASSED
tests/test_quota.py::test_request_that_would_exceed_limit_is_rejected_429 PASSED
tests/test_quota.py::test_past_due_subscription_gets_402_regardless_of_quota PASSED
```
Boundary is exact: 999→1000 allowed, 1000→1001 rejected (429, message
includes "quota exceeded"). A `past_due` subscription gets 402
regardless of remaining quota headroom (message includes `past_due`).

## Cost calculation

**Monthly usage rolls up into a cost figure per tenant.**
```
GET /usage → { "api_calls_used": 1000, "api_calls_limit": 1000,
               "ai_tokens_used": 0, "ai_tokens_limit": 100000,
               "cost_cents": 100 }
```
(1000 API calls @ $0.001/call = $1.00 = 100 cents.)

**AI token pricing handles cached input, reasoning, and output tokens correctly.**
```
tests/test_pricing.py::test_cached_input_tokens_are_cheaper_than_fresh_input PASSED
tests/test_pricing.py::test_reasoning_tokens_billed_at_output_rate_not_input_rate PASSED
tests/test_pricing.py::test_categories_are_priced_independently_then_summed_not_flat_rate PASSED
```
1M cached-input tokens costs 75¢ vs 1M fresh-input tokens costs 300¢.
500k reasoning tokens costs exactly what 500k output tokens costs
(750¢) — same bucket, not a separate rate. Mixed-category request
(200k input + 800k cached + 100k output + 50k reasoning) = 345¢,
matching independent per-category pricing summed, not a flat rate.

**Pricing constants are pinned and covered by tests.**
```
app/services/pricing.py — TOKEN_PRICE_CENTS_PER_MILLION, API_CALL_PRICE_CENTS_PER_CALL
tests/test_pricing.py — 8 tests, all pinned to exact cent values
```

## Stripe integration

**Subscription checkout works end-to-end in Stripe test mode.**
```
tests/test_webhooks.py::test_valid_checkout_completed_webhook_flips_tenant_to_pro PASSED
```
A verified `checkout.session.completed` event flips `tenant.plan_id`
from `free` to `pro`; `/usage` immediately reflects the Pro limit
(50,000 vs 1,000 API calls).

**Webhooks verify signatures, ignore duplicate events, and update tenant plan/status.**
```
tests/test_webhooks.py::test_forged_signature_is_rejected_and_nothing_changes PASSED
tests/test_webhooks.py::test_replayed_real_event_is_processed_exactly_once PASSED
tests/test_webhooks.py::test_subscription_deleted_reverts_tenant_to_free PASSED
```
A forged `Stripe-Signature` header → `400`, tenant plan unchanged. The
same real event id delivered twice → first call `duplicate: false`,
second call `duplicate: true`, and tenant state reflects exactly one
application, not two. `customer.subscription.deleted` reverts a tenant
to `free`.

### Live Stripe test-mode verification (real Checkout, not just automated tests)

In addition to the pytest suite (which signs its own fake events), the
full flow was run against real Stripe test-mode infrastructure using
the Stripe CLI and a live Checkout Session.

**1. `stripe trigger` fixtures — end-to-end webhook delivery, all accepted:**
```
2026-08-10 15:21:43  --> product.created [evt_1U2qKxGUIpzHECROT3XWUpQX]
2026-08-10 15:21:43 <-- [200] POST http://localhost:8000/webhooks/stripe
2026-08-10 15:21:44  --> price.created [evt_1U2qKyGUIpzHECRODtITyzU3]
2026-08-10 15:21:44 <-- [200] POST http://localhost:8000/webhooks/stripe
2026-08-10 15:21:49  --> charge.succeeded [evt_3U2qL2GUIpzHECRO0iq5vWvD]
2026-08-10 15:21:49 <-- [200] POST http://localhost:8000/webhooks/stripe
2026-08-10 15:21:49  --> payment_intent.succeeded [evt_3U2qL2GUIpzHECRO0Uy360mW]
2026-08-10 15:21:49 <-- [200] POST http://localhost:8000/webhooks/stripe
2026-08-10 15:21:49  --> checkout.session.completed [evt_1U2qL3GUIpzHECROMiyWIrG8]
2026-08-10 15:21:49 <-- [200] POST http://localhost:8000/webhooks/stripe
2026-08-10 15:21:52  --> charge.updated [evt_3U2qL2GUIpzHECRO0dRi95d8]
2026-08-10 15:21:52 <-- [200] POST http://localhost:8000/webhooks/stripe
```
Matching app-side log:
```
api-1  | INFO: 172.20.0.1:44296 - "POST /webhooks/stripe HTTP/1.1" 200 OK
api-1  | INFO: 172.20.0.1:41860 - "POST /webhooks/stripe HTTP/1.1" 200 OK
```
Confirms real Stripe signature verification passes against actual
Stripe test-mode infrastructure — not just the self-signed fixtures in
`tests/test_webhooks.py`.

**2. Real Checkout Session created via `/billing/checkout` for tenant `demo-free`:**
```
POST /billing/checkout   X-Tenant-Id: demo-free
→ { "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1i75egBukdxFBHjZbKwXKUXpltYdSBvQVgMFhjI6kQZR1OPo2wEBHOEeA",
    "session_id": "cs_test_a1i75egBukdxFBHjZbKwXKUXpltYdSBvQVgMFhjI6kQZR1OPo2wEBHOEeA" }
```
Opened the returned `checkout_url` in a browser (Stripe-hosted
Checkout page, "Sandbox" badge visible, £29.00/month Pro Plan), paid
with Stripe's test card `4242 4242 4242 4242` (any future expiry, any
CVC). Redirected successfully to `/billing/success`:
```
{"status":"ok","session_id":"cs_test_a1i75egBukdxFBHjZbKwXKUXpltYdSBvQVgMFhjI6kQZR1OPo2wEBHOEeA","message":"Checkout complete — webhook will sync your plan."}
```

**3. Confirmed the webhook actually applied — before vs after:**

Before (seeded state):
```
plan: free, api_calls_limit: 1000, ai_tokens_limit: 100000
```

After (`GET /usage`, `X-Tenant-Id: demo-free`):
```json
{
  "tenant_id": "demo-free",
  "plan": "pro",
  "period": "2026-08",
  "api_calls_used": 995,
  "api_calls_limit": 50000,
  "ai_tokens_used": 0,
  "ai_tokens_limit": 5000000,
  "cost_cents": 100
}
```

Confirms the complete real-world path: Checkout Session creation →
hosted payment page → signed webhook delivery → signature verification
→ tenant plan sync — working end-to-end against actual Stripe
test-mode infrastructure, not simulated. This is the live version of
the §13 demo moment ("Run a Stripe test-mode Checkout → the webhook
fires → the tenant flips from Free to Pro live").

## Data model, tests & documentation

**Database includes tenants, plans, subscriptions, and usage events; customer data isolated per tenant.**
```
app/models.py — Plan, Tenant, UsageEvent, ProcessedStripeEvent
alembic/versions/0001_initial_schema.py — migration creating all four tables
```
Every usage query is scoped by `tenant_id` (see
`app/services/metering.py::usage_totals_for_period`); the unique
constraint on `usage_events` is itself scoped per-tenant.

**Tests cover: duplicate usage prevention, quota boundary cases, cost calculations, invalid-webhook rejection, duplicate-webhook handling.**

Full suite:
```
$ pytest -v
tests/test_idempotency.py::test_same_idempotency_key_creates_one_usage_event PASSED
tests/test_idempotency.py::test_different_idempotency_keys_create_separate_events PASSED
tests/test_idempotency.py::test_same_idempotency_key_different_tenants_are_independent PASSED
tests/test_pricing.py::test_fresh_input_tokens_priced_at_input_rate PASSED
tests/test_pricing.py::test_cached_input_tokens_are_cheaper_than_fresh_input PASSED
tests/test_pricing.py::test_reasoning_tokens_billed_at_output_rate_not_input_rate PASSED
tests/test_pricing.py::test_reasoning_and_output_tokens_combine_in_the_same_bucket PASSED
tests/test_pricing.py::test_categories_are_priced_independently_then_summed_not_flat_rate PASSED
tests/test_pricing.py::test_zero_usage_costs_nothing PASSED
tests/test_pricing.py::test_small_token_counts_round_half_up_not_truncated PASSED
tests/test_pricing.py::test_api_call_cost_is_linear_and_pinned PASSED
tests/test_quota.py::test_request_that_lands_exactly_on_limit_is_allowed PASSED
tests/test_quota.py::test_request_that_would_exceed_limit_is_rejected_429 PASSED
tests/test_quota.py::test_request_just_under_limit_is_allowed PASSED
tests/test_quota.py::test_a_single_large_request_that_would_overshoot_is_rejected PASSED
tests/test_quota.py::test_past_due_subscription_gets_402_regardless_of_quota PASSED
tests/test_quota.py::test_retry_after_rejection_still_fails_until_capacity_frees PASSED
tests/test_webhooks.py::test_forged_signature_is_rejected_and_nothing_changes PASSED
tests/test_webhooks.py::test_valid_checkout_completed_webhook_flips_tenant_to_pro PASSED
tests/test_webhooks.py::test_replayed_real_event_is_processed_exactly_once PASSED
tests/test_webhooks.py::test_subscription_deleted_reverts_tenant_to_free PASSED

============================== 21 passed in 0.38s ==============================
```

**README + architecture diagram + setup instructions; submission-pack files present.**
```
README.md, capstone.yaml, EVIDENCE.md, BUILDLOG.md, .env.example — all present at repo root
```

**Full stack verified running clean via `docker compose up`:**
```
db-1   Healthy
api-1  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
api-1  | Seed complete: plans=[free, pro], tenants=[demo-free @ 995/1000 calls, demo-pro @ 0]
api-1  | INFO:     Application startup complete.
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
```