# Design

`discover_experiment` reuses the existing adapter class but is never registered
as a schedulable entry point. It reads only the retained-date listing, date
listings and available 00z/12z product listings. Candidates are formed from
filenames actually present upstream and carry run, lead, valid time and exact
member/control URLs. The ordinary `discover` calls the registry gate first.

At retrieval, the sidecar identity must match the candidate's date, cycle and
lead. Each selected member/field range must answer 206 with an exact
`Content-Range` and byte count. The range is checksummed, decoded and cropped to
the exact Avalon box. Evidence capture retains every range and index; offline
replay verifies their identity and checksums, rebuilds an identical artifact,
then exercises the core reader through a test-only HTTP route. Every decoded
coordinate array must be identical across fields and members; xarray is not
allowed to align different grids and fill the difference with nulls.

AIFS ENS joins `pf` members 1..50 and the separate `cf` control 0 on one member
axis. IFS Open Data currently exposes only `pf` members 1..50 in `enfo-ef`.
The original retained artifact stays partial with control 0 missing and no
claimed retrieval location. ECMWF's Cycle 50r1 documentation says `enfo:cf`
was discontinued and designates bit-identical `oper:fc` as its replacement.

On 2026-09-05, owner `@TusharSariya` explicitly authorized the bounded choice
in issue 82: **“yeah approved go”**
([canonical approval](https://github.com/TusharSariya/Astraeus/issues/82#issuecomment-5553992154)).
This authorizes this experiment, and only this experiment, to map the six
selected `oper:fc` fields (`tcc`, `2t`, `2d`, `10u`, `10v`, `msl`) to IFS ENS
control member `0`. The mapped records retain their original `oper` stream,
`fc` type and URL metadata alongside the explicit Cycle 50r1 producer mapping.
They must match the perturbed records' run, lead, valid time, units,
instantaneous cloud semantics and exact grid. A missing or inconsistent mapped
record leaves the result incomplete. Arbitrary `fc` records remain ineligible
for `member_of`; no other substitution or inferred path is authorized.

This authorization does not change a V1 normative status, registry declaration,
scheduler, production API schema or operational status. The mapped control is
reachable only through an explicit candidate detail on the unregistered
experiment seam.

The representative live operation retains each selected source record and
writes one cropped Zarr artifact per family. Its actual 651,145,054 input bytes,
receipts, indexes, artifacts and replay outputs fit the 4 GiB scratch
reservation with the required 8 GiB co-worker and 1 GiB physical margin. The
operation does not alter the daily cap setting or 64 GiB hot-storage quota.

Evidence: `docs/research/wayfinder/ecmwf-ensemble-bounded-retrieval.md`.
Receipts for the `ecmwf-ensemble-20260905-corrective` capture (URL, request
parameters, byte counts, checksums, capture time, artifact revision) and the
condensed API readbacks:
`docs/research/wayfinder/evidence/ecmwf-ensemble-20260905/`. Provider payloads
are not retained in Git, per the owner decision of 2026-09-05 recorded in
issue #70; replay inputs are re-captured locally with
`experiments/st-johns-weather-map/scripts/ecmwf_ensemble_evidence.py`.
