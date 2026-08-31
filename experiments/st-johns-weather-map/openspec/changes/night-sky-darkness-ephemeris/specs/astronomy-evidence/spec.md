## ADDED Requirements

### Requirement: Astronomy values come only from the pinned, verified ephemeris
Every astronomical value served SHALL be computed from the single pinned JPL
DE442 kernel whose sha256 is declared in code, verified against the local
file before first use in each process. A missing, unreadable or
checksum-mismatched kernel SHALL make the astronomy capability answer
unavailable with the stated reason; nothing SHALL be computed from an
unverified file, no fallback ephemeris SHALL be substituted, and the rest of
the API SHALL be unaffected. Download SHALL happen only in the out-of-band
fetch script, never in a request handler or at process start.

#### Scenario: Missing kernel fails closed
- **WHEN** no kernel file exists at the configured path
- **THEN** `/astronomy` answers `data_mode: unavailable` naming the missing
  kernel, and no band or moon value is served

#### Scenario: Checksum mismatch fails closed
- **WHEN** the file at the configured path does not hash to the pinned sha256
- **THEN** `/astronomy` answers `data_mode: unavailable` naming the mismatch,
  and the file is not used

#### Scenario: No in-process download
- **WHEN** the kernel is absent and `/astronomy` is requested repeatedly
- **THEN** no network fetch of the kernel is attempted by the API process

### Requirement: The computation is disclosed and bounded
Every `/astronomy` response SHALL carry one provenance block naming the
source `nasa-jpl-de442`, the Skyfield version, the kernel id and sha256 in a
derivation string, a derivation version, and `operational: false`. The
response SHALL cover exactly the evidence window; a reference instant outside
the window SHALL be 422, and a coordinate outside the core bounds SHALL be
422, exactly as for point evidence. Twilight bands SHALL use the standard sun
altitudes (-0.833, -6, -12, -18 degrees) and moon rise/set the stated
horizon rule, each named in the derivation text.

#### Scenario: A served window disclosed end to end
- **WHEN** `/astronomy` answers for the default coordinate
- **THEN** the response carries the window start and end, the twilight bands,
  moon rise/set/phase/illumination, and a provenance block with source id,
  kernel sha256, Skyfield version and `operational: false`

#### Scenario: Outside the window
- **WHEN** a reference instant beyond the window edge is requested
- **THEN** the response is 422 naming the window, and no bands are returned

### Requirement: The Milky Way core window is geometry and says so
The galactic-centre window SHALL be computed purely as the intersection of
core altitude above 5 degrees, sun altitude below -18 degrees and moon below
the horizon, from the pinned ephemeris and the fixed J2000 coordinates of
Sgr A*. It SHALL be named `geometric_core_window`, SHALL carry the maximum
core altitude over the window, and its caption SHALL state that it is
geometry only - no cloud, transparency or light-pollution factor SHALL be
folded in, here or in the interface.

#### Scenario: Geometry only
- **WHEN** the core window is served while the cloud layers show overcast
- **THEN** the window is unchanged by the cloud evidence and its caption
  states that it says nothing about cloud, transparency or light pollution

#### Scenario: No window tonight
- **WHEN** the intersection is empty over the evidence window
- **THEN** the response says there is no geometric core window rather than
  omitting the field, and still reports the maximum core altitude
