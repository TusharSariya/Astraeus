# ADSB.lol Mode S weather disposition

Date: 2026-09-06

Status: non-normative research for #115. No API request, raw feed, aircraft
record, account, key, or paid service was used.

## Decision evidence

ADSB.lol's first-party API documentation says the API is available to
everyone, identifies the API data license as ODbL 1.0, and documents dynamic
rate limits and a possible future feeder-issued key requirement. Its API is a
tracking API compatible with the ADSBExchange Rapid API, and its spatial query
selects aircraft inside a circle or rectangle. It does not document a weather
product, weather-only response, fixed observation network, Avalon station, or
coverage guarantee.

- <https://github.com/adsblol/website/blob/main/content/en/docs/open-data/api.md>
- <https://github.com/adsblol/api/blob/main/src/adsb_api/app.py>
- <https://github.com/adsblol/api/blob/main/README.md>

ADSB.lol identifies `readsb` as a component of its service. The upstream
`readsb` output contract documents four weather-looking aircraft fields:

| Output | Upstream meaning | Disposition |
| --- | --- | --- |
| `wd`, `ws` | Calculated from ground track, true heading, true airspeed, and ground speed | Derived aircraft-state estimate; not a direct weather observation contract |
| `oat`, `tat` | Calculated from Mach and true airspeed; documented as inaccurate at lower altitude/Mach and inhibited below Mach 0.395 | Derived aircraft-state estimate; not a direct thermometer observation contract |
| `nav_qnh` | Selected navigation pressure setting | Aircraft intent/state; not ambient pressure |
| BDS 4,4 static pressure | The decoder source contains a pressure-valid bit and static-pressure payload | No corresponding documented `aircraft.json` output field or ADSB.lol API contract was found |

The field semantics and BDS 4,4 decoder evidence are in the upstream source
used by ADSB.lol:

- <https://github.com/wiedehopf/readsb/blob/dev/README-json.md#aircraftjson-and---json-port>
- <https://github.com/wiedehopf/readsb/blob/dev/comm_b.c>
- <https://github.com/adsblol/website/blob/main/content/en/docs/acknowledgements/open-source.md>

The free API therefore offers weather-looking values only inside records for
recently tracked aircraft. Consuming them would necessarily collect aircraft
identity, position, motion, and recency data. A bounding box around Avalon
would select transient aircraft rather than a stable geographic observation
source, and an empty response could mean no aircraft reception rather than no
weather. No raw tracking collection was performed to test coverage.

## Permission disposition

The first-party service labels the API and public data ODbL 1.0. That supplies
a concrete database-license starting point, including attribution and
share-alike obligations for applicable public reuse. It does not by itself
resolve Astraeus's product-level attribution, derivative-database, produced
work, retention, and redistribution design. Historical and raw feeder products
also consist of aircraft tracking and are outside this audit.

- <https://www.adsb.lol/docs/open-data/historical/>
- <https://github.com/adsblol/globe_history_2026/blob/main/LICENSE-ODbL.txt>
- <https://www.adsb.lol/docs/feeders-only/beast-mlat-out/>

## Disposition and owner choice

No eligible ADSB.lol weather field contract is available for #115 under the
current constraints. Mark this source **deferred/unavailable** for the Avalon
weather map: the public API couples derived estimates to raw tracking records,
does not expose documented ambient pressure, and provides no stable Avalon
coverage or weather-product semantics. Keep completion false and QC unknown.

The owner can make one of two bounded choices:

1. Exclude ADSB.lol from #115 because it is an aircraft tracking source whose
   documented weather-looking fields are derived estimates.
2. Authorize a separate proposal for derived aircraft meteorology, including
   whether aircraft tracking may be collected, the `readsb` calculation and
   uncertainty contract, altitude/time/geography sampling semantics, sparse
   coverage behavior, ODbL delivery obligations, and source QC. Direct BDS 4,4
   meteorology would require a separate raw Mode S acquisition and decoder
   contract and remains outside the authorized scope.

This audit does not close #115; the remaining product contracts stay pending.
