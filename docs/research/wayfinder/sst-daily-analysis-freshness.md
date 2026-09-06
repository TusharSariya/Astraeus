# SST daily-analysis freshness evidence

Non-normative evidence for issue #153. No SST field payload was downloaded in this follow-up.

The [Copernicus OSTIA product page](https://data.marine.copernicus.eu/product/SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001/description) identifies `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` as a daily, Level-4, 0.05-degree analysis with a daily 12:00 update. Its public anonymous Zarr metadata at `2026-09-06T06:02:34.462918Z` still identified `2026-09-04T00:00:00Z` as the newest native analysis, about 54.0 hours old.

The [NOAA OISST v2.1 metadata](https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc%3AC01606/html) states that preliminary files are produced daily with one-day latency, may be updated during the first few days, and are replaced by final products after two weeks. A bounded 1,784-byte listing request completed at `2026-09-06T06:02:51.538166Z`; SHA-256 `4ee252113babd539e7f5e73eaca7dacf30e6265f6d963f331aa56a84ab7c1fe9`. The latest advertised analysis date was `20260904`, making the native 12:00 center about 42.0 hours old. The compact local receipt remains at `/tmp/sst153-freshness-audit/oisst-listing-receipt.json` pending review.

The earlier independently reviewed capture at `2026-09-06T00:15Z` found the same September 4 analyses. Both checks therefore fail the accepted `now-24h` observation boundary during normal public availability. Re-fetching unchanged data cannot solve the mismatch.

The recommended owner choice is a narrowly scoped 60-hour native-valid-time ceiling for these two daily analyses, paired with aged-out refusal and no fallback. It changes neither the general 24-hour observation rule nor the 14-day forecast horizon. Registration remains blocked until complete-operation resource bounds are implemented and verified.
