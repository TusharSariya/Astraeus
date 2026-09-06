# Pending publication contracts: source-first decision brief

Date: 2026-09-06

This is non-normative decision support for the corrective source-first sequence
recorded in `docs/handoffs/handoff.md`. It consolidates five draft pull requests;
it does not accept a contract, change a protected status, register a source, or
make an artifact publishable.

## Recommendation

Decide only contracts that immediately unlock a complete path into the existing
application. Accept the RAQDPS/RDAQA field package in PR172 and the source-specific
SST freshness package in PR179. Accept the structural GeoJSON package in PR168
only for a bounded CAP-alert implementation through the existing feature/layer
surface. Defer PR167 because its reference inputs have no existing weather-view
consumer. Defer PR175 until redistribution authority for the rendered images and
an existing-web display path are both pinned; image structure alone cannot grant
rights or make a source visible.

These are five independent representation or policy choices, not one shared
manifest framework. None authorizes science, scoring, operational promotion, or
a new visual rebuild.

## Decisions

### 1. PR172: RAQDPS/RDAQA numeric fields — accept the proposed package

The retained experiment has all 28 selected coverages and the existing Zarr
point reader can consume numeric fields once their identities are canonical.
The smallest coherent choice is PR172's exact 28-coverage mapping, deterministic
`mol mol-1` to `nmol mol-1` scaling, native particulate units, vertical scope,
smoke attribution, 24-hour statistic metadata, and five separate phase streams.
Provider QC remains unknown and the source remains experimental.

Alternatives that duplicate keys per phase or preserve gas values under separate
upstream-unit keys increase catalogue/API complexity without preserving more
source information. Permanent nonpublication is honest but leaves a verified
eligible numeric source out of the app.

**Owner question 1:** Approve PR172's recommended canonical field and five-phase
package for experimental implementation, with no science/admission promotion?

### 2. PR179: OSTIA/OISST daily analysis freshness — accept 60 hours

The existing 24-hour observation rule repeatedly excludes normal daily products:
measured latest ages were 54 hours for OSTIA and 42 hours for OISST. Retrieval
time cannot make old analysis current. A source-specific 60-hour native-valid-time
ceiling is the narrowest tested choice that admits both observations while
leaving the general 24-hour window unchanged. Only the newest eligible analysis
is routable; after 60 hours it is aged out with no fallback.

Keeping 24 hours means these eligible sources remain permanently unavailable.
Forty-eight hours already fails the observed OSTIA case; 72 hours adds an
unmeasured extra cycle.

**Owner question 2:** Approve PR179's 60-hour `daily_l4_analysis` ceiling for only
OSTIA and OISST?

### 3. PR168: native GeoJSON alerts — accept narrowly for CAP feature delivery

The existing application already has layer/feature semantics for GeoJSON. Native
CAP properties can remain source fields without inventing canonical hazard
meaning. The minimum contract is structural validation, provider QC unknown,
producer times only when present, retrieval time used only as provenance, a
24-hour acquisition-age refusal for untimed query snapshots, bounded artifact
size, and current plus previous retention with the previous revision audit-only.

Activation still needs populated-response size evidence; five empty seasonal
collections cannot justify the 40 MiB ceiling. Acceptance does not authorize
SCRIBE or unknown-schema products and does not translate alerts into scientific
weather fields.

**Owner question 3:** Approve PR168's native structural GeoJSON branch only for
bounded CAP-alert feature/layer delivery, contingent on measured populated-size
bounds?

### 4. PR175: Holyrood rendered GIFs — defer pending rights and a current UI path

PR175 correctly limits the product to opaque paired rain/snow images with unknown
source QC, no numeric pixel meaning, exact pair identity, six-minute cadence,
18/60-minute freshness, and 24-hour retention. Those semantics are coherent.
However, the retained source was treated as local-only under an all-rights-reserved
notice, and the proposal adds revision-addressed routes that the existing web does
not consume. Accepting image structure alone would not resolve redistribution or
complete provider-to-existing-app delivery.

**Owner question 4:** Keep PR175 deferred until a cited redistribution basis and
a minimal existing-web layer route are supplied, or explicitly authorize
local-only experimental display under the stated terms?

### 5. PR167: IERS/NAIF reference inputs — defer until a named consumer exists

The proposed reference-input manifest is internally bounded: atomic companions,
one current revision, a 64 MiB aggregate sub-budget within 64 GiB, provider
expiry or accepted max age, and up to seven audit revisions for 30 days. But the
current Map, timeline and point views do not consume these resources. It would
add a separate experimental route and retention class without completing a
weather source in the existing app.

This is a consumer-scope blocker rather than a storage-schema emergency. The
captured resources can remain nonpublishable research evidence until an existing
view or accepted derivation names them.

**Owner question 5:** Defer PR167 and retain the inputs as nonpublishable evidence
until a specific existing-app consumer is approved?

## Effects of the recommended choices

Approving PR172, PR179 and the narrow PR168 contract removes representation or
freshness blockers; each source still needs source-specific finite resource
bounds, normal worker publication, real API readback, existing-web consumption,
and independent evidence review. PR175 remains blocked by rights and delivery,
and PR167 by absent consumer need. No choice closes #133, #137, #153, #105 or
#123 by itself.

Sources:

- [PR167 reference inputs](https://github.com/TusharSariya/Astraeus/pull/167)
- [PR168 native GeoJSON](https://github.com/TusharSariya/Astraeus/pull/168)
- [PR172 RAQDPS/RDAQA](https://github.com/TusharSariya/Astraeus/pull/172)
- [PR175 Holyrood images](https://github.com/TusharSariya/Astraeus/pull/175)
- [PR179 daily SST freshness](https://github.com/TusharSariya/Astraeus/pull/179)

Spec-Impact: none; decision brief only.
