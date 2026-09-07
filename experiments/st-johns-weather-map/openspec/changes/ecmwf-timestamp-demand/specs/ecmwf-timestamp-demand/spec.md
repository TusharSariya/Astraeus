## ADDED Requirements

### Requirement: ECMWF demand products preserve exact native identity
Each ECMWF demand response SHALL identify one of ecmwf-ifs, ecmwf-ens,
ecmwf-aifs-single or ecmwf-aifs-ens with its producer model/version basis,
distributed grid, run, lead, valid time, field, level, units and native interval.
Only actually published exact-time records SHALL be eligible. Pinned-run
failure SHALL NOT choose another run, product or nearest step. Initial fields
SHALL be verified native 2t/2d in K at2m, msl in Pa atmean-sea-level, and
instantaneous entire-atmosphere tcc fraction, normalized only through accepted
catalogue rules with original units preserved.

#### Scenario: An AIFS field is absent while IFS has a value
- **WHEN** AIFS has no eligible record for the requested native instant
- **THEN** AIFS remains unavailable and IFS is not substituted

#### Scenario: A selected lead has different temporal support
- **WHEN** requested instantaneous cloud is supplied as a time average
- **THEN** the record is rejected rather than relabelled

### Requirement: ECMWF ensemble members remain explicit and incomplete families stay partial
AIFS ENS SHALL preserve pf members1..50 and separate cf control0. IFS ENS SHALL
preserve pf members1..50 in enfo:ef and MAY use producer-designated Cycle50r1
oper:fc control0 only for tcc,2t,2d,10u,10v,msl after exact run/lead/grid/level/unit
matching. Original stream/type/URL and the mapping SHALL remain in provenance.
Absent members SHALL be named and completeness SHALL remain partial. Fields or
members from different grids, runs or model families SHALL NOT be silently
joined, regridded or substituted. Ensemble values SHALL NOT replace deterministic
values or create additional independent forecast-centre votes.

#### Scenario: IFS designated control is absent
- **WHEN** perturbed records exist but the eligible mapped control does not
- **THEN** control0 is missing and the family is explicitly partial

#### Scenario: A member has a different coordinate array
- **WHEN** one member's native grid differs from its family
- **THEN** it is rejected without automatic array alignment or regridding

### Requirement: ECMWF live queries are bounded and cache only while relevant
A canonical key SHALL include product/version basis, run, lead, member/field
selection and spatial window. Discovery, index input, range input, decoder
memory/time/output and cache byte/entry counts SHALL have finite enforced
limits. Fresh hits SHALL issue no provider requests; identical misses SHALL
coalesce. Expiry and failed refresh SHALL withhold values. Receipts SHALL
preserve canonical/effective requests, safe headers, byte counts, hashes and
final-byte retrieval/expiry separately from native run/valid times. Delivery
SHALL NOT require full-run ingestion, a permanent ArtifactStore or an archive.

#### Scenario: Several clients request the same native selection
- **WHEN** the canonical cache key is identical
- **THEN** one bounded acquisition supplies the shared fresh entry

#### Scenario: Expired values cannot refresh
- **WHEN** acquisition fails after expiry
- **THEN** public values remain absent with typed source-specific failure
