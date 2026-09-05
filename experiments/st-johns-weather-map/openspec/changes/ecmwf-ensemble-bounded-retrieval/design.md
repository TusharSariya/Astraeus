# Design

`discover_experiment` reuses the existing adapter class but is never registered
as a schedulable entry point. It reads only the retained-date listing, date
listings and available 00z/12z product listings. Candidates are formed from
filenames actually present upstream and carry run, lead, valid time and exact
member/control URLs. The ordinary `discover` calls the registry gate first.

At retrieval, the sidecar identity must match the candidate's date, cycle and
lead. Each selected member/field range must answer 206 with an exact
`Content-Range` and byte count. The range is checksummed, decoded, cropped to
the exact Avalon box and deleted. Every decoded coordinate array must be
identical across fields and members; xarray is not allowed to align different
grids and fill the difference with nulls.

AIFS ENS joins `pf` members 1..50 and the separate `cf` control 0 on one member
axis. IFS Open Data currently exposes only `pf` members 1..50 in `enfo-ef`.
That artifact stays partial with control 0 missing and no claimed retrieval
location. Deterministic `oper` output is a different product and is never used
as an inferred control.

The representative live operation retains at most one global record at a time,
then writes one cropped Zarr artifact. Its actual 651,145,054 input bytes and
two artifacts fit the 4 GiB scratch reservation with the required 8 GiB
co-worker and 1 GiB physical margin. The operation does not alter the daily
cap setting or 64 GiB hot-storage quota.

Evidence: `docs/research/wayfinder/ecmwf-ensemble-bounded-retrieval.md`.
