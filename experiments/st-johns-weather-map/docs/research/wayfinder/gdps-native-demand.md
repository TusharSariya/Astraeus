# ECCC GDPS selected-time demand DQC (#237)

This is non-normative evidence for an experiment. It does not change a
specification status, make the source operational, or complete #189/#194.

## Provider product identity

The official ECCC MSC Datamart dated tree exposes the atmospheric GDPS forecast
under `/{YYYYMMDD}/WXO-DD/model_gdps/15km/{00|12}/{FFF}/`. A bounded listing on
2026-09-06 exposed hourly lead directories 000 through 240. Its five selected
objects use `LatLon0.15` filenames: `AirTemp_AGL-2m`, `DewPoint_AGL-2m`,
`WindSpeed_AGL-10m`, `WindDir_AGL-10m`, and `Pressure_MSL`. The separate 10 km
tree exposed only `GDPS-Analysis_IICECONC` NetCDF and is not an atmospheric
forecast fallback.

Wind speed and meteorological from-direction are provider-published scalar
objects. The selected path returns the direction unchanged in degrees and does
not derive from or rotate the separate U/V messages.

Official documentation: https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps_en/
Provider tree: https://dd.weather.gc.ca/20260906/WXO-DD/model_gdps/15km/

## Bounded implementation

The canonical key carries cycle URL, provider run, lead, sorted fields and
Avalon crop. The Linux child enforces a 2 GiB address-space ceiling inside the
measured 4 GiB aggregate container cgroup,
finite input/output/stderr/stdout/workspace limits and a 180-second timeout.
The source-local cache admits at most four entries and 32 MiB aggregate backing
for no more than ten minutes. Identical misses coalesce. Expired values are
removed before replacement; a failed replacement exposes only bounded
acquisition identity for at most one further TTL. No retained artifact, archive,
full-run prefetch, neighbouring frame or stale fallback is read.

## Native proof

One production-path capture retained the five native f011 objects for run
`2026090612`, valid `2026-09-06T23:00:00Z`. The nine original HTTP receipts
(four directory listings and five objects) total 5,132,349 bytes; their compact
receipt has SHA-256
`8e7328b043c3b72fe130f37e06f24d39a0abda80fab58d5046faf43e8fd42558`.
The latest payload final byte completed at `2026-09-07T00:48:21.405847Z`.

Image `astraeus-gdps-api@sha256:6d642f7d0f7a5ef5b95891de400c40f004f0ddf51dd5fda990c6b0dbca48ff6c`
replayed those retained bytes through the production coordinator and bounded
child on an internal Docker network with no provider route. The selected run,
lead, five native fields, QC and unit normalization passed. The normalized ZIP
was 17,594 bytes with SHA-256
`ce8c1218a2bac7e53113d9f7ebb67c01909a25dfdfd764bf748084980e778c38`.
A fresh repeat returned the same cache object and added zero replay requests.
The compact capture and replay receipts remain outside Git under
`/private/tmp/gdps237-live/`; no provider bytes enter the repository.
