## ADDED Requirements

### Requirement: Every derived-here value names an enabled registry entry
The deployment SHALL keep a derivation method registry. Every entry SHALL
declare a stable name, a version, a citation to the published physical or
statistical construction it implements, the catalogue fields it reads as
inputs, the catalogue field it produces, the physical range of its output and
the rule applied when the range is exceeded, and an `enabled` flag. No value
of class `derived_here` SHALL be produced by a method that is not an enabled
registry entry. A method SHALL NOT be fitted to the outputs it produces.

#### Scenario: An unregistered method
- **WHEN** code attempts to publish a derived value naming a method absent from the registry
- **THEN** publication fails with `unregistered_method` and nothing is served

#### Scenario: A registered, enabled method
- **WHEN** a value is produced by an enabled entry
- **THEN** its provenance carries the entry's name, version and citation, and the input fields it declared

### Requirement: Registration is owner-approved and refuses blending
Adding or changing a registry entry SHALL require the owner's approval,
recorded in the entry. An entry whose inputs include the same catalogue field
from more than one source, or that combines a provider reduction with a
statistic over another member set, SHALL be refused at registration as
blending.

#### Scenario: An entry without approval
- **WHEN** an entry is added with no approval record
- **THEN** the registry fails validation and the deployment refuses to start with it

#### Scenario: A blending entry
- **WHEN** an entry declares inputs `total_cloud_opacity_weighted` from HRDPS and `total_cloud_geometric` from GFS with one output
- **THEN** registration is refused naming the rule

### Requirement: A method can be disabled at three levels
A method SHALL be disableable per entry (`enabled: false`), per deployment
by environment variable, and per reader in the interface, mirroring the
generated-display kill switch. A disabled method SHALL produce `null` with a
notice, never a substitute construction.

#### Scenario: Deployment-level refusal
- **WHEN** the deployment environment variable refuses derivations
- **THEN** every `derived_here` field is `null` with a notice naming the variable, and retrieved values are unaffected

#### Scenario: Reader-level refusal
- **WHEN** a reader switches a method off in the interface
- **THEN** that reader's view shows the field as switched off, and no other reader is affected

### Requirement: The first registered entries are the derivations already served
The following constructions SHALL be registry entries before this change is
applied: relative humidity from temperature and dew point (liquid phase,
MetPy); wind speed and direction from u and v; the ensemble statistics (mean,
spread, quantiles, threshold probabilities, counts) within one family and
run; sector sampling of a gridded field along a bearing from a site; and the
Sun and Moon geometry fields from the pinned DE442 ephemeris.

#### Scenario: Relative humidity is served after this change
- **WHEN** relative humidity is derived for a source that published none
- **THEN** its provenance names the relative-humidity registry entry, and the value carries `evidence_class: derived_here`
