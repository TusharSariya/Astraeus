# WeatherNext 3 surface point delivery

Classification: experiment. Owner authorization: on 2026-09-08 the owner requested
WeatherNext 3 historical and forecasting delivery, hiding WeatherNext 2, and
confirmed “yes do it all” for all 126 surface statistic fields.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

This amendment replaces the temperature-only consumer restriction for the
isolated local experiment. Production registration, scheduling, raw members and
pressure-level access remain excluded. No normative status transition is made.

## ADDED Requirements

### Requirement: All provider surface statistics
The local experiment SHALL expose all 21 native surface fields with mean, p10,
p25, p50, p75 and p90 as distinct selectable readings. Each individual point request SHALL fetch
only its selected field/statistic through the existing bounded statistics reader.
Native units, grid, null mask, run, valid time and object receipts SHALL survive.
Temperature SHALL be represented in degC, cloud fraction in percent, pressure
in hPa and accumulated precipitation in mm. Hourly precipitation and solar
energy SHALL retain their one-hour accumulation semantics. Provider percentiles
SHALL never be reconstructed from members or marked computed here.

#### Scenario: Fields are selected
- **WHEN** a user selects a field and provider statistic
- **THEN** only that exact native array is acquired and its native identity is disclosed

#### Scenario: Native data is absent
- **WHEN** a land SST cell is masked or a request exceeds a resource bound
- **THEN** missingness is retained without a fabricated value or substituted source

### Requirement: Native timeline selection
Historical and local forecast paths SHALL retain distinct scopes and select the
first native hourly forecast valid time at or after the selected timeline instant
within the configured or discovered published run. The native coordinate reader SHALL verify
the selected lead exists. Exact legacy calls SHALL remain exact. A historical
forecast SHALL remain a forecast, and SHALL not be rejected merely because its
run is historical. No out-of-run time or unsupported member SHALL be substituted.

#### Scenario: Timeline is between native hours
- **WHEN** a selection falls between two hours in the configured run
- **THEN** the following native hour is returned with the original selection retained

### Requirement: Legacy source visibility
Both Google and Open-Meteo WeatherNext 2 entries SHALL be hidden from discovery
and selection while their source ledger records remain available for audit.
WeatherNext 3 SHALL retain its explicit provider identity.

#### Scenario: Sources are browsed
- **WHEN** the user browses or searches sources
- **THEN** WeatherNext 2 is absent and WeatherNext 3 surface readings are discoverable

### Requirement: Bounded published run discovery
The opted-in internal runtime SHALL discover the newest available main-cycle
root at or before the selected instant (with at least one hour lead) and real
clock, probing at most four six-hour cycles under 15 seconds and 64 KiB metadata.
Successful native metadata SHALL pin generation, ETag and size before science
access. Discovery SHALL retain at most 16 roots for five minutes. Only declared
2026 archive paths SHALL be requested; unavailable backfill remains a gap.
All-field point selection SHALL remain individual bounded reads, with two frontend
requests at a time. The September 9 comparison amendment below permits selected-field batches. No raw-ensemble billing project SHALL be supplied.

#### Scenario: A run has not yet been published
- **WHEN** the newest nominal cycle has no root metadata
- **THEN** the next earlier candidate is checked within the same finite budget

#### Scenario: Authentication or discovery fails
- **WHEN** no permitted published root can be resolved
- **THEN** point data remains unavailable and no alternative identity is used

### Requirement: Runtime source consistency
The local web proxy SHALL target its own Compose project's API container, so
a separately running workbench API on the same network cannot supply an older
catalogue or point implementation through a shared service alias.

#### Scenario: Two API experiments share a network
- **WHEN** both containers advertise the generic api service name
- **THEN** this application's proxy consistently selects its own project API

### Requirement: Bounded native Avalon cloud grid
Owner authorization: the 2026-09-08 implementation request explicitly authorizes
this experimental amendment under GOV-SPEC-001, GOV-SPEC-004 and GOV-SPEC-006.
The isolated experiment SHALL offer optional grid capability, unsupported by
default, only for total, low, middle and high cloud ensemble means in historical and internal forecast
scopes. A typed source-grid request SHALL retain selected/native time, pinned
run/object identity, native coordinate axes, shared midpoint cell boundaries,
nullable percentages and acquisition provenance. The complete intersecting
native footprints SHALL cover Avalon (west -55, south 46.5, east -51, north
48.5), including water; only display boundaries SHALL be clipped. Each required
chunk SHALL be acquired once, with existing auth, discovery, lead verification,
historical cutoff and process/resource limits. The Atlantic demand-cloud amendment adds a named Atlantic region while retaining
Avalon as the API default. Responses SHALL be at most 2 MiB;
the scope/run/object/native-time/field/region cache SHALL hold at most four
frames and 8 MiB, expire after 60 seconds, and coalesce duplicate requests.
Grid and point acquisition SHALL share a two-request bound. Map + data SHALL
start grid acquisition first and reuse that frame for the corresponding point;
Data only and legacy point requests SHALL retain direct point delivery.

#### Scenario: Complete grid agrees with points
- **WHEN** a selected native frame is acquired
- **THEN** each intersecting cell is extracted once with native ordering and longitude conversion, shared boundaries, null masks and valid zeroes
- **AND** point reads within that frame agree at identical run/time/field, including boundary and cached reads

#### Scenario: Grid unavailable or replaced
- **WHEN** credentials, run, lead, receipt or resource validation fails, or evidence expires
- **THEN** no stale replacement picture or fabricated value is returned
- **AND** duplicate requests coalesce while obsolete client responses are discarded

### Requirement: Native cloud grid display
Forecast and historical total, low, middle and high cloud means SHALL be selectable using Off, Map +
data, Data only. Saved point-only selections and default profiles SHALL remain
unchanged. Adjoining native geographic rectangles SHALL use fixed tint and
alpha equal to cloud fraction times layer opacity, with no smoothing,
subdivision or spatial interpolation. The legend SHALL name ensemble-mean
cloud cover and explain that alpha is a display mapping, not physical optical
opacity. Valid zeroes SHALL be transparent and inspectable; missing cells SHALL
use a distinct neutral pattern and legend entry. Existing details SHALL expose
percentage, native centre/footprint, statistic, run, valid time and provenance.
Panning, zooming and opacity SHALL reuse the selected frame. Timeline changes
SHALL cancel obsolete work; failed replacement frames SHALL clear the old
picture and disclose failure. No forecast sequence SHALL be prefetched.

#### Scenario: Display and inspection preserve meaning
- **WHEN** zero, 50%, 100% and missing cells are rendered
- **THEN** opacity follows the stated mapping, missingness is distinct, and every cell remains inspectable

#### Scenario: Selection survives and remains bounded
- **WHEN** selection cycles, saved point-only state is restored, or viewport changes
- **THEN** point identity is retained and only Map + data acquires the selected grid frame
- **AND** desktop themes and sizes at normal and 200% browser zoom retain usable Layers and timeline controls

### Requirement: WN3 available-time markers
Owner authorization: the 2026-09-08 follow-up requests timeline markers for
available historical and future WN3 cloud readings. This remains an experiment.
Active WN3 point selections, including Data only, SHALL contribute native valid
times to the existing timeline and previous/next navigation. A bounded inventory
request SHALL read published root and native initialization/lead coordinates,
validate the selected field metadata, and acquire no science chunks. At most two
runs (covering the requested window's ends) SHALL be inventoried per request;
missing archive roots SHALL remain explicit gaps. A window SHALL span at most
15 days. Historical markers SHALL obey the existing strict 48-hour cutoff.
Markers SHALL disclose forecast valid time and initialization separately and
SHALL describe availability as a native time axis, not a downloaded cloud value.
Inventory SHALL share the two-request WN3 limit, coalesce identical run/field/scope
reads, cache at most four entries for 60 seconds, and bound each acquisition to
1 MiB, 30 seconds and 10 operations. Obsolete responses SHALL not restore markers.
No forecast sequence SHALL be downloaded to create timeline dots.

#### Scenario: Point or grid selection contributes its time axis
- **WHEN** a WN3 selection is enabled in Map + data or Data only
- **THEN** actual native timestamps appear as selectable markers and navigation targets
- **AND** opacity changes and clicking a marker do not fetch an entire sequence

#### Scenario: Inventory is unavailable or historical
- **WHEN** metadata, credentials, scope or native coordinates cannot be validated
- **THEN** unavailable inventory is disclosed without invented cadence markers
- **AND** historical timestamps at or newer than the cutoff are withheld

### Requirement: Comparison batches selected published statistics
Owner authorization: the September 9 multiple-model comparison implementation request.
A comparison SHALL discover and pin native run/time coordinates, then batch the
selected surface means and optional matching P10/P90 fields in one native point
acquisition per source/run/time. The existing bounded worker SHALL reuse shared
coordinate metadata and native chunks within that batch. The original byte,
decode, credential, native-mask and receipt checks SHALL remain enforced.
Unsupported quantities, including relative humidity and direction statistics,
SHALL remain absent. This changes neither individual point calls nor production
status. Comparison page and lifetime limits are owned by desktop-evidence-api.

#### Scenario: Several charts use the same forecast position
- **WHEN** temperature, cloud and precipitation means with published spread are selected
- **THEN** one native acquisition contains the exact requested arrays and all
  emitted readings retain one batch identity and their own units/statistics

#### Scenario: A selected batch reaches the existing byte ceiling
- **WHEN** some selected fields have decoded successfully and another field would exceed the source byte or operation ceiling
- **THEN** the batch retains completed fields, records the unread field as a budget gap, preserves receipts for metadata already consulted, and does not acquire its payload or invent a value


### Requirement: Dedicated WeatherNext workspace
Owner authorization: the September 9 dedicated WeatherNext workspace implementation
plan. The isolated experiment SHALL implement the section, product, percentile,
threshold, shared timeline, pinned run, bounded paging and expiry semantics in
[the workspace contract](workspace.md). This supersedes the total-cloud-only grid
restriction, with no change to production or normative status.

#### Scenario: Shared selection is explored
- **WHEN** WeatherNext is opened or docked
- **THEN** only the active section loads for the selected point and full shared range
- **AND** native times retain one pinned run, source provenance and explicit gaps

#### Scenario: Published summaries support an estimate
- **WHEN** a threshold is entered or changed
- **THEN** the backend reads retained percentiles without provider acquisition
- **AND** strict quantile neighbors bracket an approximate range, ties widen it,
  and non-monotonic or unusable data withholds the estimate

#### Scenario: Pages load, expire or are cancelled
- **WHEN** a page is pending or fails, the selection changes, or evidence expires
- **THEN** completed results remain independently inspectable while fresh,
  expired values are withheld, and cancelled selections start no later pages

### Requirement: Owner-selected one GiB acquisition budget
Owner authorization: on September 9 the owner explicitly requested raising the
WeatherNext download limit to 1 GB, implemented as 1 GiB (1,073,741,824 bytes).
The experimental native delivery SHALL allow at most 1 GiB total received bytes
per acquisition, including metadata, with matching parent, worker and receipt
validation. The lower standalone bridge default SHALL remain 16 MiB. Individual
compressed objects SHALL remain bounded to 64 MiB, decoded chunks to 128 MiB,
and process memory, concurrency and native worker deadlines SHALL remain
unchanged. Workspace page waiting and retained-summary expiry SHALL follow the
subsequent owner-authorized live loading correction in `workspace.md`; other
source consumers retain their existing deadlines and expiry. Selected point batches SHALL support up to 36 fields, as required by
the Wind section. Their operation allowance SHALL be max(30, 10 + 4 × fields),
capped at the native reader's existing 270-operation maximum. Grid and inventory
operation limits SHALL remain 30 and 10 respectively. This amendment supersedes
the workspace's previous aggregate-byte/operation restriction only; it does not
authorize raw members, requester billing, production status or unbounded reads.

#### Scenario: A larger selected statistics batch is read
- **WHEN** aggregate metadata and science bytes exceed 64 MiB but remain within 1 GiB
- **THEN** byte validation permits the batch while all per-object, memory, native
  identity and time constraints remain enforced

#### Scenario: A resource bound is exceeded
- **WHEN** a batch exceeds 1 GiB, a chunk exceeds 64 MiB, or a time/process limit is reached
- **THEN** the acquisition refuses excess work and retains existing explicit failure semantics
