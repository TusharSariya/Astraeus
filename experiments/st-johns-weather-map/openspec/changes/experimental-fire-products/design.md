# Design

| Access path | Native fields / disposition |
| --- | --- |
| CWFIS `hotspots_last24hrs` WFS | GeoJSON geometry and every producer property are retained verbatim. The selected Avalon query was observed-empty, so it has no invented field or source-time claim. |
| CWFIS dated hotspot CSV | `lat,lon,rep_date,source,sensor,fwi,fuel,ros,sfc,tfc,bfc,hfi,estarea`: header and each row are retained verbatim. `rep_date` remains an unparsed native string. |
| CFFEPS dated CSV | `lat,lon,rep_date,source,sensor,ffmc,dmc,dc,ws,fwi,fuel,ros,sfc,tfc,bfc,hfi,estarea`: header and each row are retained verbatim. No value is labeled an emissions rate. |
| NASA FIRMS public active-fire index | Canada 24-hour MODIS, SNPP, NOAA-20 and NOAA-21 CSV rows retain `latitude,longitude,brightness/bright_t31/bright_ti4/bright_ti5,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight` when published. Times and numeric strings remain native; units, mask and quality semantics are uncontracted. The separate area API is MAP_KEY-gated and receives no credential request. |
| RAQDPS FireWork | Superseded, excluded |
| BlueSky | Unverified machine feed/licence, excluded |

The public source indexes are `https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/`,
`https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows`, and
`https://firms.modaps.eosdis.nasa.gov/api/active_fire_files/all?format=json`.

Each listing, WFS document, and CSV response has a finite streaming ceiling,
records URL, headers, byte count, SHA-256 and the transport completion time,
and is stored as immutable source bytes. GeoJSON structure and UTF-8 CSV
header/row widths are validated; malformed, empty, over-ceiling, or unsafe
indexed inputs fail closed and remove partial artifacts. CSV values, including
native `rep_date`, `acq_date`, `acq_time`, confidence and numeric-looking
values, are never coerced or normalized. No decoder constructs a numeric
field, quality value, fire perimeter, emission rate, or API response. Every
result is made nonpublishable by the unresolved manifest owner gate; it remains
unregistered and `operational: false`.
