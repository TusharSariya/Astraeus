# Tasks

- [x] Draft reference identity, time, validity, QC, geography, publication, read-routing, window and retention requirements.
- [x] Separate computed structural validation from owner-authorized scientific suitability.
- [x] Record one concrete recommended owner policy and its alternatives without implementing it.
- [ ] Owner reviews and accepts, revises, or rejects the proposed contract.
- [ ] Only after acceptance: implement manifest, validator, storage group, strict API models and mapped verification.
- [ ] Test plan: manifest construction rejects missing epoch scale, version rule, byte ceiling, temporal policy, expiry policy, spatial scope and retention declaration.
- [ ] Test plan: validator computes missing member/field, bad units, malformed epoch, date/MJD mismatch, expired revision, uncovered consumer interval and decode-error failures; no adapter supplies its own pass verdict.
- [ ] Test plan: atomic publication failure leaves the prior group current; read integrity failure rejects the whole group; members from two revisions never mix.
- [ ] Test plan: strict API lookup accepts source/logical resource and requested interval, carries no fabricated coordinates or sample time, excludes unknown fields, and returns unavailable for expired, uncovered, scientifically ineligible or unreadable inputs under the accepted experimental-only visibility policy.
- [ ] Test plan: quota projection and the accepted aggregate-budget, supersession, expiry and retention policy are exercised with no cold tier; reference epochs never enter `/timeline` or point/layer sampling.
