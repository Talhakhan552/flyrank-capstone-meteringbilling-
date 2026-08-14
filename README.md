# Usage Metering & Billing Engine

FlyRank Internship — Backend Track capstone. A small backend that answers
the three questions every SaaS needs answered: how much has this tenant
used, what does it cost, and have they hit their limit — correctly, under
retries, failures, and real-world conditions.

## What it does

- **Meters usage** for two types (API calls, AI tokens), exactly once per
  request even under retries, via an idempotency key.
- **Enforces quotas** before allowing a billable action, with honest
  `429` (quota exceeded) vs `402` (subscription not payable) responses.
- **Calculates cost** in integer cents, with the real AI-token pricing
  rules: cached input is cheaper, reasoning tokens bill as output, and
  categories are priced independently then summed.
- **Syncs plans from Stripe** (test mode) via signature-verified,
  deduplicated webhooks — the database only ever mirrors what Stripe
  confirms happened.

## Architecture

```
Client ──► POST /generate  (X-Tenant-Id, Idempotency-Key)
             │
             ▼
        [FastAPI router: app/routers/usage.py]   ← HTTP concerns only
             │
             ▼
        [QuotaService]  current usage + requested → allow / 429 / 402
             │ allowed
             ▼
        [MeterService]  insert usage_event; unique(tenant_id, idem_key)
                         constraint violation on retry → return original
             │
             ▼
        [PricingService]  price this event in integer cents (Decimal math)

GET /usage ◄── rollup(usage_events for period) → { used, limit, cost }

Client ──► POST /billing/checkout ──► Stripe Checkout Session (test mode)
                                              │
                                       customer "pays" with 4242 4242…
                                              │
Stripe ──signed webhook──► POST /webhooks/stripe
             │
             ▼
        verify signature (forged → 400)
             │
             ▼
        claim event id once (replay → 200, no-op)
             │
             ▼
        apply_event() → tenant.plan_id / subscription_status updated
```

Layering: **routers** (HTTP only) → **services** (all business logic:
metering, quota, pricing, Stripe) → **models** (SQLAlchemy, one row per
concept). Swapping Postgres for another database, or Stripe for another
payment provider, only touches `app/database.py` or
`app/services/stripe_service.py` — never the routers.

## Data model

- `plans` — Free / Pro, quotas and Stripe price id baked in.
- `tenants` — one row per customer org; every query elsewhere is scoped
  by `tenant_id`.
- `usage_events` — one row per billable action; `UNIQUE(tenant_id,
  idempotency_key)` is what makes metering exactly-once — the database
  constraint is the idempotency mechanism, not an application-level
  check-then-insert (which would race under concurrent retries).
- `processed_stripe_events` — dedup ledger for inbound webhooks, keyed
  by Stripe's own event id.

Money is always an integer number of cents. Internal pricing math uses
`Decimal`, never `float` — see `app/services/pricing.py`.

## Run it

```bash
git clone <your-repo-url>
cd billing-engine
cp .env.example .env   # fill in Stripe test-mode keys (optional — the
                        # app boots with placeholders; only /billing/checkout
                        # and /webhooks/stripe need real Stripe test keys)
docker compose up
```

This starts Postgres, runs migrations, seeds two demo tenants, and boots
the API on `http://localhost:8000` (interactive docs at `/docs`).

Demo tenants after seeding:
- `demo-free` — Free plan, seeded to 995/1000 API calls (boundary is 5 requests away).
- `demo-pro` — Free plan, fresh, for the checkout → webhook demo.

### Running tests

```bash
pip install -r requirements.txt
pytest -q
```

Tests run against an in-memory SQLite database (no Docker/Postgres
needed) and don't require real Stripe credentials — webhook tests
construct and sign their own test events using the same HMAC scheme
Stripe uses, so signature verification is exercised for real.

### Local webhook testing against Stripe

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
stripe trigger checkout.session.completed
```

## Quota boundary rule

A request is rejected if `current_usage + requested_quantity > limit`.
A request that lands **exactly on** the limit is allowed; the next one
is rejected. Rejected requests are never recorded — there is nothing to
"partially fulfill" and nothing for a retry to replay.

## Limitations (honest, on purpose)

- No invoicing, proration, or overage billing — out of scope per the
  brief (§7); Free/Pro with hard quotas only.
- Tenant auth is a header (`X-Tenant-Id`), not an API key or JWT — a
  real product would resolve tenant identity from an authenticated
  principal; that only touches `app/dependencies.py`.
- AI token counts are simulated inputs to `/generate`, not real model
  calls — the brief explicitly doesn't require an AI key.
- No reconciliation job against Stripe's view — listed as a stretch
  goal, not implemented in core.


## Demo

[6-minute walkthrough](https://drive.google.com/file/d/1jlkH2O9l_mZUzfgzK9_aht01mgmv4fie/view?usp=drivesdk) — covers quota boundary
enforcement, idempotent retries, a live Stripe test-mode Checkout
flow, forged/replayed webhook handling, and the full test suite
passing.