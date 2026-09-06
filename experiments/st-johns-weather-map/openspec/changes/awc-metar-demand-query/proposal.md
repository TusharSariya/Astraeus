# CYYT METAR selected-time demand query

## Why

Issue #214 migrates the already bounded `awc-metar-speci` experiment from scheduled publication to the owner-selected timestamp-demand architecture. PR #185 remains historical acquisition evidence; this change does not relabel it as demand-cache proof.

## What changes

- Resolve each aware selected time to a canonical two-hour AWC request ending at the UTC hour ceiling, using official `date` and `hours` selectors.
- Cache at most 64 complete 64 KiB responses, coalesce identical requests, and revalidate only under provider validators and finite freshness headers.
- Select the latest CYYT observation at or before the requested instant only when its age is strictly less than one hour.
- Serve the observation through the existing `/point`, Brief, and Workbench paths without requiring ArtifactStore health.
- Disable scheduled `awc-metar-speci` acquisition after the demand path is proven.

The experiment remains `operational: false`; no source admission, new derivation, bulk archive, or stale fallback is introduced.

## Native-field disposition

The bounded provider body remains the audit source. The point response exposes
the selected report's identity without repeating the raw report text: station,
optional provider report id, observation/report/receipt times, METAR/SPECI type,
raw-report SHA-256, provider station name/coordinate/elevation, flight category,
and provider QC code travel as `provenance.native_report`.

| AWC JSON keys | Demand response disposition |
| --- | --- |
| `icaoId`, `obsTime`, `metarId`, `metarType`, `rawOb`, `reportTime`, `receiptTime` | Bounded report identity; `rawOb` is exposed by digest, not repeated text |
| `name`, `lat`, `lon`, `elev`, `fltCat`, `qcField` | Provider-native report metadata; the registered CYYT coordinate remains the sampling geometry |
| `temp`, `dewp` | Canonical temperature/dew point; relative humidity is the existing registered derivation |
| `slp` | Canonical mean sea-level pressure |
| `altim` | Native altimeter value only; it is not relabelled as mean sea-level or surface pressure |
| `wspd`, `wdir`, `wgst` | Native wind metadata; canonical speed/direction come from the existing u/v derivation and gust is served when present |
| `visib` | Canonical visibility with native statute-mile value retained |
| `cover`, `clouds`, `vertVis` | Native aggregate/layer/vertical-visibility metadata; recognized layer cover/base values are served canonically, while an unmappable code such as `OVX` stays an explicit canonical absence |
| `wxString` | Native weather string plus existing explicit fog/vicinity-fog/mist evidence flags; no other weather meaning is inferred |

Absent optional keys remain absent in the native metadata and cannot be
relabelled as a decoded value. Any provider key outside this finite inventory,
or a populated key with the wrong structure, refuses the whole response.
