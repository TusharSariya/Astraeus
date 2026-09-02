## Why

The wayfinder effort finished its admission tickets on 2026-09-02. Four owner
resolutions (tickets
[24](https://github.com/TusharSariya/Astraeus/issues/24),
[25](https://github.com/TusharSariya/Astraeus/issues/25),
[26](https://github.com/TusharSariya/Astraeus/issues/26) and
[28](https://github.com/TusharSariya/Astraeus/issues/28)) decided, source by
source, what may be retrieved for the evidence box, by what access path, and
why. Nothing in the specification records those decisions, and the registry
that is supposed to be the single catalogue cannot express most of them.

Two concrete gaps make that plain.

First, the state vocabulary. `CONTEXT.md` names ten registry states
(operational, implemented-unverified, catalogued, credential-blocked,
licence-blocked, link-only, partnership-only, unavailable, rejected,
superseded). `registry/schema.json` carries a different nine-member `status`
enum (`active`, `implementing`, `credential_required`, `licence_review`,
`unavailable`, `duplicate_evidence`, `unsupported_field`, `retired`,
`rejected`). They are not the same list. Today 50 of 63 records sit on the
single value `implementing`, which conflates a source with a registered
adapter and a passing fixture against a source that is a paragraph of prose,
and there is no value at all for link-only or partnership-only. The
resolutions decided states the schema cannot store: REWPS is rejected, the
CYYT radiosonde is unavailable, FireWork is superseded by RAQDPS smoke-plume
layers, the NRCan STJ magnetometer is partnership-only, 7Timer is link-only.

Second, the credential rule. Ticket 25 set a standing rule that ticket 26
restates: a credential-gated source is admitted as `credential-required` and
fails closed until the owner supplies keys through the secrets workflow. The
existing requirement "Credentials live only in the environment and their
absence is honest" in `openspec/specs/artifact-ingestion/spec.md` covers
secrecy and per-source isolation but never says that admission does not imply
retrieval, that no prepared URL may be logged, and that the source's declared
state does not move when the key arrives or when it does not. The same
resolutions admitted restricted-terms sources (UKMO share-alike, Falchi
CC BY-NC 4.0, NL 511 no-reuse, WeatherNext 2 real-time terms) for research use
only, and nothing in the specification records terms or forbids
redistribution.

Evidence and its limits are stated plainly. Every admission below rests on a
live probe recorded in a research file under `docs/research/wayfinder/` on a
`research/*` branch, cited by path in `design.md`; that research is
non-normative. What is unverified: the Atlantic-domain check for RDWPS and
GDWPS, the Meteosat limb-geometry cost that conditions the LSA SAF radiation
admission, the WMS re-probe for integrated nowcasting, the CWOP and CelesTrak
licence texts, and the NC-SPACES product inventory. Each is carried as a
declared condition on the record, not as a promise. This change proposes no
display of any value that cannot be retrieved: an admission is a ceiling, and
every state below stays under the rule that no live retrieval promotes a
source.

This change writes the vocabulary, the two standing rules and the ledger into
the specification. It edits no adapter and promotes no source to
`operational`.

## What Changes

- **Ten registry states, reconciled with the schema.** The state vocabulary in
  `CONTEXT.md` becomes the registry's own, and this change states exactly how
  each current `status` value maps onto it: `implementing` splits into
  `implemented-unverified` and `catalogued` on an objective test; `retired`
  splits into `superseded` and `unavailable` on whether a successor is named;
  `credential_required` becomes `credential-required` (the glossary's
  "credential-blocked"); `licence_review` becomes `licence-blocked`;
  `duplicate_evidence` folds into `superseded`; `unsupported_field` folds into
  `unavailable`; `link-only` and `partnership-only` are new; `active` maps to
  `operational` and, as today, is never emitted for any source under any
  circumstance.
- **Credential-required is an admission that fails closed.** A record in that
  state is admitted, declares the credential it needs and the registration
  page, and is not schedulable. With no credential resolved at runtime no
  adapter fetches, no prepared URL is logged, no value is served, and the
  state does not move.
- **Research-use-only admission.** A record MAY declare restricted terms; it
  then carries the terms verbatim with their source, is never redistributed,
  and its values are served to the owner's own reader only. A record that
  declares restricted terms without terms text fails the audit.
- **The admissions ledger.** Every source named in the four resolutions gets a
  decided state, an access path and a recorded reason. Nineteen records are
  new (CelesTrak GP, five SWPC products, GFZ Hp30, GOES magnetometer and X-ray,
  Kyoto Dst via SWPC as reprocessed, CAMS AOD and LSA SAF radiation and GFS
  Wave via Open-Meteo, JMA GSM, ARPEGE, UKMO and MOSMIX via aggregators, the
  Falchi atlas, Coast Guard NAVWARN, the NL provincial air-quality CSV, and
  Open-Meteo's WeatherNext 2 cloud as intermediary-derived), and existing
  records change state (REWPS rejected, radiosonde unavailable, FireWork
  superseded, KMA, CMA and GraphCast unavailable, STJ magnetometer
  partnership-only, Nav Canada cameras moving from licence review to
  credential-required through the owner's NC-SPACES account).
- **Absence is specified for every admitted source.** A record's state says
  what happens when its source is absent: a credential that never resolves, an
  endpoint that dies under an admitted record, a licence that blocks, a
  partnership that is not granted. In each case the answer is a stated absence
  with provenance, never a substitute value and never a state change.
- **One licence correction.** The CAMS record's licence text is corrected to
  the ADS catalogue's CC BY 4.0, which the registry currently contradicts.
- **Delivery kind is referenced, not redefined.** Every reprocessed and
  intermediary-derived admission here declares its delivery kind under the
  unarchived change `openspec/changes/ensemble-members-and-source-plurality/`,
  extended by `openspec/changes/evidence-classes-and-derived-here/`. This
  change adds no delivery kind of its own.

## Capabilities

### Modified Capabilities

- `source-registry-catalogue`: adds the ten-state vocabulary and its mapping
  from the current status enum, the credential-required fail-closed admission,
  research-use-only admission with recorded terms, the ledger requirement that
  every resolved source carries state, access path and reason, and the rule
  that link-only and partnership-only records are declarations and never data
  paths. Modifies the ceiling requirement and the schedulability requirement
  so they speak the new vocabulary while keeping every existing scenario.
- `artifact-ingestion`: modifies "Credentials live only in the environment and
  their absence is honest" so that a missing credential is a fail-closed
  admission rather than an error state, and adds the no-redistribution rule
  for restricted-terms sources and the behaviour when an admitted source's
  endpoint dies.

## Impact

- `registry/schema.json`: the `status` enum is replaced by the ten-state
  vocabulary; new required blocks for credential admission (`credential`
  name and registration URL) and restricted terms (`terms_text`,
  `terms_source_url`, `redistribution: false`).
- `registry/source_data.py`: 19 new records, 8 state changes, the CAMS licence
  correction, and the state migration of all 63 existing records. Not edited
  by this change; the per-record edits are described as tasks.
- `registry/audit.py`: state-vocabulary validation, the credential and
  restricted-terms rules, and the refusal of `operational`.
- `api/weather_api/`: the ceiling table gains the new states; link-only and
  partnership-only are never schedulable and never emit an access endpoint a
  caller could fetch.
- `CONTEXT.md`: the glossary line for registry state gains the note that
  "credential-blocked" is the state written `credential-required`.
- No adapter retrieval logic changes, no source is promoted, `operational`
  stays unreachable and `operational: false` stays on every response.
  Spec-Impact: none outside this experiment.
