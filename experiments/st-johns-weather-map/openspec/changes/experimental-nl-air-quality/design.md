# Design: exact provisional station series

The adapter binds only source `nl-air-quality-csv`, station `StJohns` / NAPS
010102 and the published rolling CSV URL. Discovery performs one streamed fetch
with a 1 MiB ceiling, validates the warning, exact schema and station identity,
then retains only rows in the requested window.

`DATE_TIME` is publisher-local wall time. It is interpreted with
`America/St_Johns` and stored as UTC, while the original offset local strings
remain in provenance. There is no invented model run; the immutable source
identity combines newest valid time and response digest.

`PM2_5_RUN_AVG` is a 24-hour running mean in µg/m³ and normalizes exactly to
kg/m³. `O3` is ppb and remains mole fraction in nmol/mol; it is not converted
to mass concentration without temperature and pressure. All six other pollutant
columns are explicitly deferred. Missing selected values remain NaN/null and
make the run incomplete without failing QC; malformed values, schema drift,
foreign station identity, missing warning, oversize and request failure fail
closed before publication.

Every value declares `uncalibrated_observation`, quality unknown with
provisional/unvalidated flags, `operational: false`, `redistribution: false`,
and no display-primary or derivation eligibility. The adapter remains under
`ingest/experimental` and is not registered or scheduled.
