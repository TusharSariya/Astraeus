## ADDED Requirements

### Requirement: L1 solar-wind series keep the measuring spacecraft and its flags per row
The real-time solar wind magnetometer and plasma series SHALL be stored on a
`valid_time x spacecraft` axis whose labels are the feed's own `source`
tokens verbatim, with the feed's `active` flag and every quality flag stored
as variables exactly as served (sentinel values kept and declared, never
converted). A spacecraft with no row at an instant SHALL hold a gap, never a
value carried from another spacecraft. The served latest Bz SHALL come from
the spacecraft the feed flagged active at that instant, named in the
response; when no spacecraft is flagged active the response SHALL say so and
name the spacecraft it served. No spacecraft SHALL be named that the feed did
not declare.

#### Scenario: Three spacecraft at one minute
- **WHEN** the feed carries SOLAR1, ACE and IMAP rows at the same minute
- **THEN** the artifact holds one cell per spacecraft at that minute, with
  each row's flags, and the reader serves `bz_gsm@SOLAR1`, `bz_gsm@ACE` and
  `bz_gsm@IMAP` separately

#### Scenario: The active spacecraft is served
- **WHEN** ACE is flagged active at the newest instant and SOLAR1 is not
- **THEN** `/space-weather` serves ACE's Bz and names ACE

#### Scenario: No spacecraft flagged active
- **WHEN** no row at the newest instant carries `active: true`
- **THEN** the response serves a value with a notice stating no spacecraft
  was flagged active and which one was served

### Requirement: Space-weather artifacts declare their measurement scope
Every space-weather artifact SHALL carry a `measurement_scope` of
`planetary`, `l1`, `propagated`, `geosynchronous`, `station` or `issued`. A
propagated product SHALL store both instants the producer gives and SHALL
derive no propagation lag. A relayed index SHALL be declared `reprocessed`
naming producer and intermediary, SHALL never be the display primary, and
SHALL be refused if declared without an intermediary. Where a feed declares
no provisional/final status the artifact SHALL say `status_declared: false`
and SHALL NOT invent one.

#### Scenario: Kyoto Dst via SWPC
- **WHEN** the Dst relay is ingested
- **THEN** the artifact is `reprocessed`, names Kyoto WDC as producer and
  NOAA SWPC as intermediary, and carries `display_primary: false`

#### Scenario: A relay declared retrieved
- **WHEN** an adapter builds provenance with class `reprocessed` and no
  intermediary
- **THEN** provenance construction fails and no artifact is written

### Requirement: A feed that is stale behind HTTP 200 is unavailable
Every space-weather adapter except alerts SHALL refuse a feed whose newest
instant is older than the evidence window start, naming that instant, and
SHALL publish nothing from it. The alerts feed SHALL record its newest issue
instant and the provider's Last-Modified instead, because an alert may
legitimately be days old. The STEREO-A relay and the hourly Kp prediction
SHALL stay `unavailable` until the owner decides on re-probe evidence.

#### Scenario: A month-old newest record
- **WHEN** a feed answers 200 with a newest instant older than 24 hours
- **THEN** discovery raises unavailability and no candidate is returned

#### Scenario: A quiet alerts feed
- **WHEN** the newest alert is three days old
- **THEN** the alerts artifact is published with that instant in provenance
  and is not refused as stale

### Requirement: Every published space-weather series can be read back
`GET /space-weather/products` SHALL list every published `space_weather`
series artifact with source, product, scope, evidence classes, producer,
intermediary where declared, retrieval receipts, stored dimensions, each
variable's units and latest finite value per label, the newest instant and
freshness against the registry threshold. An artifact that cannot be read
SHALL be reported as skipped with its reason; fixture mode SHALL answer
unavailable; nothing SHALL be substituted for an absent artifact.

#### Scenario: Products listed
- **WHEN** Hp30 and GOES X-ray artifacts are published
- **THEN** both appear with their scopes, receipts and latest values, the
  X-ray values per satellite label

#### Scenario: Fixture mode
- **WHEN** the API runs in fixture mode
- **THEN** the endpoint answers unavailable and lists no product
