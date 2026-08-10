# Design doc — Usage Metering & Billing Engine

**Problem.** Answer three questions correctly, under retries and
failures: how much has a tenant used, what does it cost, and have they
hit their plan limit.

**Data model.** `plans` (Free/Pro + quotas) → `tenants` (plan_id,
subscription_status, Stripe ids) → `usage_events` (tenant_id,
usage_type, quantity, idempotency_key UNIQUE per tenant, period) +
`processed_stripe_events` (dedup ledger for inbound webhooks).

**API surface.**
- `POST /generate` — dummy billable action (metering + quota + pricing)
- `GET /usage` — rollup: used / limit / cost for current period
- `POST /billing/checkout` — Stripe Checkout Session (test mode)
- `POST /webhooks/stripe` — verified, deduplicated webhook handler

**Layer sketch.** routers (HTTP only) → services (metering, quota,
pricing, stripe — all business logic) → models (SQLAlchemy). See
README.md for the full flow diagram.

**Non-goal.** No invoicing, proration, or overage billing in core —
Free/Pro with hard quotas only, per brief §7.
