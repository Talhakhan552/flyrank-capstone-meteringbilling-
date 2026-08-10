## Live Stripe test-mode verification (in addition to automated tests)

`stripe trigger checkout.session.completed` fired a real signed webhook
through `stripe listen`, verified end-to-end against the running app:

--> checkout.session.completed [evt_1U2qL3GUIpzHECROMiyWIrG8]
<-- [200] POST http://localhost:8000/webhooks/stripe [evt_1U2qL3GUIpzHECROMiyWIrG8]

Confirms: real Stripe signature verification passes, webhook is
accepted and processed (200, not 400), against actual Stripe test-mode
infrastructure — not just the self-signed test fixtures in
tests/test_webhooks.py.