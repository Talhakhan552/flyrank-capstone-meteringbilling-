# Build Log

Honest account of AI involvement, per the capstone's ground rules
(§3): "AI-assisted building is encouraged — and owned."

## What AI (Claude) generated

The full initial implementation — models, services (metering, quota,
pricing, Stripe), routers, migrations, Docker setup, and the test suite
— was scaffolded by Claude in one working session, from the capstone
brief PDF directly. All 21 tests were run and passed against the
generated code before being committed.

## What I (Talha) need to do before this is really "mine"

This log is a starting point, not a finished record — fill these in as
you go, per the brief's instructions:

- [ ] Read every file in `app/services/` line by line. These three
  files (`metering.py`, `quota.py`, `stripe_service.py`) are where the
  three "genuinely hard parts" the brief calls out actually live.
- [ ] Be ready to explain, unprompted: why `record_usage()` attempts
  the insert first and catches the constraint violation, instead of
  checking-then-inserting (race condition under concurrent retries).
- [ ] Be ready to explain the `>` vs `>=` boundary decision in
  `quota.py::check_quota` (`used + requested_qty > limit` — a request
  landing exactly on the limit is allowed).
- [ ] Run `docker compose up` yourself, watch it seed and boot, hit
  `/docs`, and manually run through the six demo steps in the brief's
  §13 before recording anything.
- [ ] Set up a real Stripe test-mode account, get real
  `sk_test_...` / `whsec_...` keys, and actually run `stripe listen` +
  `stripe trigger checkout.session.completed` locally — the webhook
  tests here sign their own fake events and never touch the real
  Stripe API, so this is the one part not yet proven against Stripe
  itself.
- [ ] Where you change anything (pricing constants, quota values,
  status code semantics), note it below with what you changed and why.

## Corrections / changes made after generation

(Add entries here as you make them — e.g. "changed API_CALL price from
$0.001 to $X because ___", or "found X was wrong, fixed by doing Y".)
