## ADDED Requirements

### Requirement: A profile is a versioned registry file, never a code path
An activity profile SHALL be a declarative, versioned file in a profile
registry checked into this repository. Each file SHALL carry a stable profile
id, a version, a human title, the field families it reads, its thresholds,
its weights, its hard stops, its graded criteria, its window rule, its site
needs and its blocked fields. Adding an activity SHALL be adding a file; no
activity SHALL have a code path of its own. A profile file that cannot be
parsed SHALL make the profile unavailable with the parse failure named, and
SHALL NOT fall back to a previous version or to a default profile.

#### Scenario: A new activity is added
- **WHEN** a new profile file is added to the registry and validation passes
- **THEN** the profile is served with no code change, carrying its id and version

#### Scenario: A profile file will not parse
- **WHEN** a profile file is malformed
- **THEN** that profile is reported unavailable naming the parse failure, every other profile still resolves, and no default profile is substituted

#### Scenario: An empty profile registry
- **WHEN** the profile registry contains no files
- **THEN** the profile list is empty with a notice, and no profile is invented

### Requirement: Every profile is validated in CI against the field catalogue
Profile validation SHALL run in CI and SHALL resolve every family name,
every field key, every level and every unit named by a profile against the
field catalogue of `field-catalogue-and-families`. An unresolvable name SHALL
fail validation and the build. Validation SHALL also refuse a threshold whose
units disagree with its field's catalogue units, a weight outside the
declared range, and a profile naming the same field in both its hard stops
and its graded criteria. Validation SHALL NOT be skippable by a profile file
flag.

#### Scenario: A profile naming an unknown family
- **WHEN** a profile names a family the field catalogue does not define
- **THEN** validation fails naming the profile, the unknown family and the file, the build fails, and the profile is not served in any data mode

#### Scenario: A threshold in the wrong units
- **WHEN** a threshold declares units the catalogue does not give its field
- **THEN** validation fails naming the field, the declared units and the catalogue units

#### Scenario: The field catalogue is unreadable
- **WHEN** validation cannot read the field catalogue
- **THEN** validation fails closed with `catalogue_unavailable` and no profile is reported valid

### Requirement: Thresholds are profile defaults plus recorded per-reader overrides
A profile SHALL declare a default value for every threshold it names. A
reader MAY override a threshold in the interface. Any override in force SHALL
be recorded in the provenance of every score it produced, naming the
threshold, the profile default and the override value. A score produced with
no override SHALL say so explicitly rather than omitting the record.
User-defined profiles are out of scope. A threshold with no declared default
SHALL fail validation.

#### Scenario: A reader overrides a threshold
- **WHEN** a reader raises the running profile's wind gust threshold and a score is produced
- **THEN** the score's provenance names the threshold, the profile default and the reader's value

#### Scenario: No override is in force
- **WHEN** a score is produced entirely from profile defaults
- **THEN** its provenance records that no threshold was overridden

#### Scenario: A threshold with no default
- **WHEN** a profile names a threshold and declares no default value
- **THEN** validation fails naming the threshold, and the profile is not served

### Requirement: Hard stops are separated from graded criteria and an unknown hard stop is not a pass
A profile SHALL declare hard stops separately from graded criteria. A hard
stop SHALL answer on its own without reference to any weight. Graded criteria
SHALL carry weights and SHALL be evaluated only when no hard stop is in
force. Lightning in range, an alert in force and precipitation above a
declared rate SHALL be hard stops wherever a profile names them. When a hard
stop's field is absent for any reason, the hard stop SHALL be reported
`unknown` and the profile SHALL disclose that it could not be checked;
absence SHALL NOT be read as the hard stop not being in force.

#### Scenario: A hard stop is in force
- **WHEN** lightning is present within the profile's declared range
- **THEN** the hard stop answers on its own, the graded criteria are not evaluated, and the reason names the hard stop

#### Scenario: A hard stop cannot be checked
- **WHEN** the lightning field is `null`, `blocked` or `aged_out`
- **THEN** the hard stop is `unknown`, the profile discloses which hard stop could not be checked and why, and no all-clear is stated

#### Scenario: A field in both lists
- **WHEN** a profile names the same field as a hard stop and as a graded criterion
- **THEN** validation fails naming the field and the profile

### Requirement: The window rule is expressed in derived-here geometry fields
Every profile SHALL declare a window rule written in the derived-here Sun and
Moon geometry fields produced by the pinned DE442 ephemeris entry of the
derivation method registry. The four first profiles SHALL use: for running,
any window of a declared length within the next 24 h, optionally restricted
to daylight; for astronomy, astronomical night; for aurora, dark hours; for
landscape photography, sunrise and sunset plus or minus a declared margin. A
window rule SHALL NOT be written in wall-clock offsets or in any solar model
other than the registered ephemeris entry. When the geometry fields are
absent, the window SHALL be reported unresolved with the absent field named,
and no window SHALL be assumed.

#### Scenario: A window resolves
- **WHEN** the astronomy profile's window is requested and the geometry fields are present
- **THEN** the window is the astronomical night boundaries and its provenance names the ephemeris entry, version and kernel

#### Scenario: The geometry fields are absent
- **WHEN** the ephemeris derivation is disabled or its output is `null`
- **THEN** the window is reported unresolved naming the absent geometry field, and the profile is evaluated over no window rather than over a guessed one

#### Scenario: A window rule not written in geometry fields
- **WHEN** a profile declares a window as a fixed local-time range
- **THEN** validation fails naming the profile and the rule

### Requirement: Blocked fields are listed explicitly in the profile
A profile SHALL list, by field key, every field it would read that no
admitted source can supply, together with the reason of licence, credential
or partnership. A profile SHALL NOT silently omit such a field. The first
profiles SHALL list: road state as blocked for running; a light-pollution
baseline as blocked for astronomy; the local magnetometer as blocked for
aurora pending NRCan permission. A field listed blocked SHALL be served in
the output contract with state `blocked` and its reason, never as `null`, and
SHALL NOT contribute to any hard stop or weight.

#### Scenario: A blocked field is read
- **WHEN** the running profile reads road state
- **THEN** the field is returned with state `blocked`, reason `licence`, the terms named, and it contributes to no hard stop and no weight

#### Scenario: A blocked field is omitted
- **WHEN** a profile would read a field no admitted source supplies and does not list it
- **THEN** validation fails naming the field and the profile

#### Scenario: A blocked field becomes available
- **WHEN** a source able to supply a listed blocked field is admitted
- **THEN** the profile file must be updated to remove the entry before the field is served, and until then the field stays `blocked`

### Requirement: The four first profiles read the family lists the owner adopted
The profile registry SHALL contain these four profiles with these family
lists, per the owner's resolution on wayfinder ticket 19:

- **Running**: temperature; dew point and humidity; wind speed and gust;
  precipitation rate and type; humidex and wind chill; UV; air quality (AQHI,
  PM2.5); radiation for wet-bulb globe; visibility; alerts; lightning;
  daylight. Road state blocked.
- **Astronomy**: every member of the cloud family; the transparency family;
  the seeing family; precipitable water; aerosol optical depth; darkness and
  Moon geometry; dew point depression; wind; fog and visibility.
  Light-pollution baseline blocked.
- **Aurora**: Kp and Hp30; solar wind speed, density and Bz; OVATION
  probability; darkness and Moon geometry; cloud in the north sector; fog.
  Local magnetometer blocked pending NRCan permission.
- **Landscape photography**: cloud in the Sun's azimuth sector by layer plus
  cloud-top height; fog and visibility; precipitation; wind; Sun geometry and
  twilight boundaries; sea state for coastal shots.

Where a profile names a sector, the sector SHALL be a parameter of the
registered sector-sampling method and SHALL declare its bearing and width.

#### Scenario: The aurora profile reads cloud to the north
- **WHEN** the aurora profile is evaluated at a site
- **THEN** the north-sector cloud value is produced by the registered sector-sampling method with the profile's declared bearing and width in its provenance

#### Scenario: A first profile's family list is changed
- **WHEN** a family is added to or removed from one of the four first profiles
- **THEN** the profile version changes and validation resolves the new list against the field catalogue

#### Scenario: A named family has no admitted member
- **WHEN** a profile names a family every admitted source fails to supply this cycle
- **THEN** each member field is served `null` with provenance, the profile discloses the empty family, and no substitute family is read

### Requirement: Every field returned to a profile carries the full output contract
Each field the evidence layer returns to a profile SHALL carry: the value;
its evidence class; its quality; its freshness; its source; its comparability
within its family; and its absence state. The absence states SHALL be
disjoint and SHALL be `null` (not retrieved, with provenance), `blocked`
(refused for a stated reason of licence, credential or partnership) and
`aged_out` (retrieved once and now outside the retention window). A `blocked`
field SHALL carry its reason and SHALL NOT be reported as `null`. A field
SHALL NOT be returned with any element of the contract omitted.

#### Scenario: A present value
- **WHEN** a profile reads a field an admitted source supplied
- **THEN** the field carries value, evidence class, quality, freshness, source and comparability, with no absence state set

#### Scenario: Blocked and null are distinguishable
- **WHEN** one field is licence-blocked and another was simply not retrieved this cycle
- **THEN** the first carries state `blocked` with its reason and the second carries `null` with provenance, and a caller can tell them apart without interpreting text

#### Scenario: An incomplete contract
- **WHEN** a field would be returned without its evidence class or comparability
- **THEN** the response fails validation for that field and the field is served `null` with `contract_incomplete` rather than served partially

### Requirement: A profile is a contract on the evidence layer only
This capability SHALL define what a profile asks the evidence layer for and
what the evidence layer answers. Scoring, ranking, recommending, choosing a
site and routing between sites are decision-layer concerns and SHALL NOT be
implemented under this capability. A profile SHALL NOT cause a value to be
substituted, blended or filled; it selects and labels evidence and nothing
more. Where this capability names a score, it constrains only the provenance
that score must carry.

#### Scenario: A profile is evaluated
- **WHEN** a profile is evaluated at a point
- **THEN** the response is the profile's fields under the output contract, and no ranking, recommendation or site choice is returned

#### Scenario: A profile cannot fill a gap
- **WHEN** a profile names a field that is absent
- **THEN** the absence is reported under the output contract and no value is interpolated, substituted or borrowed from another field or source
