# Tasks

- [x] Thread the aware selected instant through the existing client and `/space-weather` route.
- [x] Add bounded canonical observed/forecast query, cache, applicability, and optional-forecast tests.
- [x] Complete freshness, conditional revalidation, failure sharing/backoff, and transport provenance.
- [x] Suppress retained Kp from `/space-weather/products` and disable its scheduler after consumer proof.
- [x] Prove actual native row inventory, miss/hit, Sky/Brief readback, and unavailable behavior.
- [ ] Run full gates and independent review.

Verification on 2026-09-06 at commit `3cfb2c8` used the bounded current
documents already acquired by the exact-head API.  The observed acquisition
was 4,786 bytes (`sha256:7b2c7d733f93b3d6bd78c0b813047657fd16f6d9d6980496aedb9477b0d606ba`)
and the forecast acquisition was 6,905 bytes
(`sha256:115e4f1399830e0d8c8e740a9ab44fe65212fa82f1f605fc4b37f50220e56d0d`).
An independent raw comparison matched all seven selected observed rows and all
18 selected forecast rows, including native timestamps, values, and forecast
status, with zero mismatches.  Each body retained its original HTTP 200
acquisition and one distinct conditional HTTP 304 revalidation event; an
immediate repeat added zero upstream request events.  Chrome displayed Kp
observed 0.67 at 12:30 p.m. NT and forecast maximum 4.67 with native
`predicted` status at 03:30 a.m. NT.  These current mutable documents do not
claim arbitrary historical coverage: selections outside their tested native
applicability return unavailable.
