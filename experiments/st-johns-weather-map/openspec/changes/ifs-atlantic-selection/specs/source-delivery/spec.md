## ADDED Requirements

### Requirement: IFS catalogue preserves product and scientific identity
The experimental reader SHALL version the official free IFS catalogue,
excluding AIFS, CAMS and explicitly unavailable products. Entries SHALL name
parameter, level, units, temporal meaning, category and rendering type.
Catalogue membership SHALL NOT claim successful retrieval. Atmosphere, soil,
ocean, wave, producer statistics, probabilities and BUFR cyclone tracks SHALL
remain distinct products. Advertised retained runs and native timestamps SHALL
be discovered per product; acquisition SHALL pin one actual run. Unreadable
inventory, unpublished records and removed runs SHALL remain distinct failures.

#### Scenario: A listed field has not yet been published
- **WHEN** its exact index record is absent from a pinned product/run/time
- **THEN** that field is explicitly unpublished and no alternative run is used

### Requirement: IFS selections are finite and resumable
One selection SHALL share a 2 GiB input ceiling across metadata, records,
predecessors and retries, with at most 4096 record acquisitions and two concurrent
acquisitions. Each record SHALL obey the existing 8 MiB ceiling and exact range
compliance. Decoding SHALL be incremental with 1 GiB memory, 16 MiB output and
64 MiB workspace limits. Records SHALL be cropped to native Atlantic cells in
70 W to 40 W and 40 N to 55 N. A bounded shared source cache SHALL coalesce
point, grid and Series reads without downloading whole multi-field objects.

Selection jobs SHALL expose cancellation, progress, bounded result pages and a
paginated transfer manifest referenced by results. Jobs SHALL retain completed
work between pages and return explicit incomplete items at exhaustion.
Comparison SHALL retain 144 source/run/time positions, 12 per page, 45 seconds,
512 KiB per page, 8 MiB response cache and fixed 15-minute lifetime. Paging,
viewing and styling SHALL NOT renew expiry. Queued obsolete work SHALL stop.

#### Scenario: The budget ends halfway through an ensemble
- **WHEN** a byte, record, deadline or lifetime ceiling is reached
- **THEN** completed work remains identifiable and uncompleted members are named

### Requirement: IFS derivations preserve native evidence
Registered wind and liquid-water humidity methods SHALL use matching source,
run, member, cell and time, retaining components, dew point and method identity.
Accumulation, average, minimum and maximum intervals SHALL be preserved.
Precipitation intervals SHALL difference only compatible cumulative records in
one run/member, acquiring the predecessor as needed; resets SHALL remain gaps.

The Cycle 50r1 producer-designated oper/fc and wave/fc controls MAY map to member
0 of the corresponding atmospheric and wave ensemble in this experiment, when
field, level, run, time, grid, units and interval match. Original stream/type
and producer mapping SHALL remain explicit. Missing control stays missing.
Registered equal-weight mean, sample standard deviation, type-7 quantiles,
threshold probability and count SHALL retain partial-member policy, member
identities and counts. Derived wind/humidity SHALL be computed per member first.
Direction angles and category codes SHALL NOT receive scalar means or bands.
Provider statistics SHALL remain distinguishable from computed statistics.

#### Scenario: A mapped control has a different interval
- **WHEN** its native interval differs from the perturbed field interval
- **THEN** the control is withheld and completeness names member 0 as missing

### Requirement: IFS maps and Series use acquired native evidence
IFS control SHALL be the fifth default comparison; ensembles SHALL be optional.
Selectors SHALL support numeric fields, levels, products, runs and variants
while retaining variable-group aliases, six selections and eight chart groups.
Grouping SHALL require matching quantity, units, level and temporal definition.
Native markers, gaps, interval bars and directional displays SHALL remain.

Each selected map capability SHALL create an independent layer with visibility,
opacity and labelled legend. Native axes, cell edges, values, units, masks and
provenance SHALL be delivered additively without changing WeatherNext responses.
Maps SHALL clip native cells to Atlantic bounds without interpolation; point
inspection SHALL sample those same cells. Cloud uses white opacity, continuous
fields use scalar legends, categories use categorical legends and bearings use
directional symbols. Cyclone tracks SHALL retain storm/member/time identity and
SHALL NOT become grid values. Ensemble mean is default with optional P10-P90;
member inspection SHALL expose acquired members and their completeness.

One bottom timeline SHALL drive map time. Chart clicks SHALL NOT move the
comparison window. Only explicit Show available window changes an empty window.
Hovering, browsing, panning, styling and loaded-member switching SHALL acquire
no science data. Expired maps SHALL withhold evidence pending Refresh; expired
comparisons SHALL remain visibly expired. Details SHALL expose calculations,
native times, runs, receipt manifest and failures.

#### Scenario: A loaded layer changes opacity
- **WHEN** the user changes opacity or inspects a loaded member
- **THEN** the same acquired native cells are reused without science requests

### Requirement: IFS verification separates fixtures and live evidence
Tests SHALL cover catalogue entries and shapes, discovery/publication/removal,
exact ranges, malformed records, levels/masks/categories/probabilities/tracks,
control mapping, derivations, resets, missing members and point/grid agreement.
Tests SHALL cover coalescing, cancellation, resumable pages, bytes, eviction,
deadlines and expiry. The real bounded decoder SHALL be proved on Linux with
fixture transport and networking disabled. Separate bounded live checks SHALL
record available control frames over 24 hours, representative profiles and
soil, full atmospheric/wave member sets, probabilities and available tracks.
Missing live products SHALL be disclosed. Affected API/client tests, generated
contracts, build, strict OpenSpec and specctl validation SHALL run, followed by
local browser inspection at normal and 200 percent zoom.

#### Scenario: Fixtures pass but a live product is absent
- **WHEN** fixture decoding succeeds but live discovery lists no product
- **THEN** evidence reports fixture success and live absence separately

### Requirement: Scientific selection compatibility is executable
This scoped experiment extends the six-field permission in
`ecmwf-ensemble-bounded-retrieval/design.md` using the owner's supplied plan and
[Cycle 50r1 slide 8](https://events.ecmwf.int/event/531/attachments/3520/5948/50r1_AIFS2_presentation.pdf).
All selected atmospheric and wave perturbed members 1 through 50 and designated
control 0 SHALL be attempted; valid matching controls SHALL be included.
Only continuous scalar ensembles SHALL default to mean and optional P10-P90.
Directions and categories SHALL expose native members without scalar reduction.

A cumulative predecessor SHALL match parameter, level, grid/cell, units,
run/member and accumulation origin with strictly ordered endpoints. Changed
origin, decreasing accumulation, incompatible identity or absent predecessor
SHALL produce an explicit interval gap. Native interval amounts SHALL NOT be
differenced. No synthetic hourly intervals are permitted.

Probability identity SHALL include event quantity, threshold value/unit/operator,
event interval and, for standardized anomalies, the producer anomaly definition.
These dimensions SHALL participate in grouping and provenance. Cyclone products
SHALL distinguish successfully decoded members predicting no trajectory from
failed member acquisition; varying storm participation is not missing grid data.

Native cache keys SHALL include product/run/time-or-interval/parameter/level/
member and grid identity. Grid response caches SHALL remain at most 8 MiB.
Selection jobs SHALL expire 15 minutes after creation, independently of paging;
45 seconds is the deadline for each page. Obsolete results SHALL be rejected.

#### Scenario: Cumulative precipitation resets
- **WHEN** a predecessor has a different accumulation origin or a larger amount
- **THEN** the interval is missing with its reset reason, never negative rain

#### Scenario: A cyclone dissipates
- **WHEN** a decoded member has no later point for one storm
- **THEN** the track ends without marking that decoded member as an acquisition failure

#### Scenario: Probability thresholds differ
- **WHEN** two percentage fields describe different thresholds or event intervals
- **THEN** their curve identities and grouping remain distinct
