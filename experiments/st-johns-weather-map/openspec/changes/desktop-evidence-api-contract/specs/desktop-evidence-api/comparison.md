# September 9 multiple-model comparison implementation decision

The owner's September 9 implementation request selects the supplied multiple-model
forecast comparison plan and authorizes amendment of the experimental contracts
before implementation. This remains an isolated experiment; no production or
normative status transition is made.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

The comparison endpoint is additive to `/point/series`. Its selection has one
location, explicit half-open start/end no more than 24 hours apart, up to six
sources/products and eight variable groups, and optional published P10/P90.
Defaults are HRDPS, RDPS, WeatherNext 3, GFS; temperature, relative humidity,
cloud, wind, precipitation; and 24 hours from initial selected time.

Acquire at most 144 distinct source/run/time positions, 12 per page, with two
concurrent acquisitions, a 45-second page deadline, 512 KiB response ceiling and
8 MiB aggregate comparison/legacy response cache ceiling. Retain source-local
byte and decoder ceilings. A fixed 15-minute lifetime starts before acquisition;
paging and viewing never renew it. Pin advertised native frames and runs.
Unreadable inventory is unknown, not confirmed absence. Completed pages appear
progressively; unsupported fields, missing coverage and credential failures
remain source-local. Cancellation stops pending pages and obsolete responses.

Continuous charts connect native samples and break at missing samples and run
boundaries; they do not resample coarser output. Precipitation retains interval
start/end in bars. Cloud opacity and geometric cover have separate aligned
subcharts. Published ensemble means and matching P10/P90 remain source-specific;
no cross-model average or uncertainty calculation is authorized. Wind speed,
gusts and optional direction remain distinct. Unsupported derived quantities
remain absent.

The shared cursor and model visibility use loaded values only. A chart click
changes map time without shifting the window. Only toolbar edits, Refresh or
Show available window change the selection. Expired charts remain visibly
expired and require Refresh. Details contains native values, provenance,
retrieval time, run segments and technical failures. No ingestion, full-grid
sequence acquisition, authentication change or operational promotion is added.

Verification maps to the owning requirements in spec.md: comparison API tests,
frontend interaction tests, contract generation checks, production build,
strict OpenSpec/specctl validation, and separately identified live/browser
proofs at normal and 200% zoom. Failed or unperformed live proofs are disclosed.

September 9 follow-up: the owner requests one timeline at the bottom. While
Series is visible it spans the fixed comparison window and drives the chart
cursor and map time, including playback without a new comparison. Hover is
temporary inspection and resets on leaving a chart. JSON property ordering is
not source/product/run identity. This remains an experiment under the same
governance references.

September 9 IFS extension: the owner's IFS plan extends this experiment with
IFS control as the fifth default, optional complete member acquisition and
field/level/variant selectors. The scoped owning contract is
`ifs-atlantic-selection/specs/source-delivery/spec.md`; its finite job budget,
identity and scientific grouping rules apply additively. Existing comparison
page/position/cache/lifetime limits remain in force.
