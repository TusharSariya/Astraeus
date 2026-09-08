# HRRR supported-Focus checkpoint

Classification: non-normative research and draft contract; #259 remains open.
Base: d4c3a47. No new GRIB acquisition, source implementation or admission.

## Recomputed native evidence

The September 7 00Z f00 surface composite-reflectivity messages retained for
#259 were replayed through actual ecCodes/Numpy in the existing Linux image,
network disabled. Their original recorded receipts are post-read/hash times,
not demand-cache final-byte receipts. These are geometry probes, not a live
meteorological point-delivery proof.

| Sector | Bytes | Native projection/dimensions | Avalon cells | Supported probe nearest native cell |
| --- | ---: | --- | ---: | --- |
| CONUS | 473251 | Lambert 1799 x 1059 | 0 | Denver: 39.7469498, -104.9863986; 0.925 km from requested 39.7392, -104.9903 |
| Alaska | 538121 | Polar stereographic 1299 x 919 | 0 | Anchorage: 61.2267746, -149.9175587; 1.337 km from requested 61.2181, -149.9003 |

All native coordinates were tested against 45..50.5 N, -58..-46 E. A supported
probe cell does not establish an arbitrary rectangular footprint. Actual
projection and cell support must guard each request.

SHA256 CONUS: `7ba19c1e951ecc3f53ee69ba5d1034971a90ff7e4d502947074d34d287377e61`.
SHA256 Alaska: `a837bb297dcc0611e9c3d0a09db18860413b2e612f5e36d270c2b6dcc8ba0c2c`.
Native parameter identity is discipline 0 / category 16 / number 196; these
captures do not prove the suggested first temperature field.

Raw messages remain `/private/tmp/hrrr259-{conus,alaska}.grib2`. Reproduction
script and recomputed JSON: `/private/tmp/astraeus-hrrr259-replay/`. Exact check:
existing `astraeus-lightning-proof:c88ff83`, `--network none --memory 1g`,
read-only capture mounts, `python /proof/replay.py`. Both hashes, projections,
dimensions, zero Avalon counts and supported probe distances passed.

## Primary documentation and reuse boundary

The [official product inventory](https://www.nco.ncep.noaa.gov/pmb/products/hrrr/)
was checked September 8 UTC. It separates CONUS/Alaska and hourly/subhourly
products, but its dated grid label for Alaska disagrees with the native
capture. Its disclaimer warns inventories can differ. Do not use that page's
forecast schedule as a current available-time listing. The
[NOAA HRRR home page](https://rapidrefresh.noaa.gov/hrrr/) separately links
experimental domains; this proposal does not silently add them.

Reuse `ingest/http.py` exact-range/receipt mechanics and `ingest/isolation.py`
process/workspace bounds. GFS query/worker illustrate source-local TTL and
selected-frame flow; `NOAAS3Adapter` is GFS-specific and is not an HRRR reader.
No existing HRRR registry source or accepted field/delivery contract was found.

The concrete draft is `openspec/changes/hrrr-selected-point/`. It preserves
Avalon exclusion and separates sector identities. Required remaining choices
are first native field contract, verified product version/current inventory,
projected-cell support and explicit resource limits. Numeric point/source API
implementation remains gated by these missing contracts, not credentials.
