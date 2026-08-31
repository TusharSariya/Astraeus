## Design

### D1 - The kernel is retrieved data, so it is a registered source

The DE442 kernel is the one retrieved input to every value served here. It is
registered as `nasa-jpl-de442` (producer NASA JPL, anonymous HTTPS from NAIF,
status `implementing`) so provenance can name a catalogued source, exactly as
for every other retrieved artifact. Its cadence prose - "static kernel;
pinned release" - deliberately fails `parse_cadence_seconds`, and its
freshness prose is "not applicable", so `ingestible` stays false and the
worker never schedules it. Verified download happened once, out of band; the
sha256 recovered from commit 5a743a8 was re-verified against NAIF on
2026-08-30 (`8d5001fab315eeff222cc51f7cf7ffcdb43fb38fb9ac73ff09e09a5b361fd388`).

### D2 - Verify-only in process; download only out of band

`api/weather_api/ephemeris.py` (recovered from 5a743a8, path made
env-configurable via `WEATHER_EPHEMERIS_PATH`) refuses a missing or
mismatched file; `scripts/fetch_ephemeris.py` is the only code that
downloads. The API boots without the kernel: only the astronomy capability
fails closed, answering `data_mode: unavailable` with the reason, because a
weather API must not die for want of a moon time. Verification runs once per
process (cached), not per request - a 114 MB sha256 per request would be a
denial of service against ourselves.

### D3 - Pure geometry functions, one provenance

`astronomy.py` computes with Skyfield against the loaded kernel: topocentric
sun/moon altitudes at the requested coordinate, altitude crossings by
bisection on a minute-resolution scan of the window for the four standard sun
altitudes (-0.833 refraction-inclusive horizon, -6, -12, -18), moon
rise/set the same way at -0.567 degrees (standard refraction + mean lunar
semidiameter is deliberately NOT applied; the plain -0.567 horizon rule is
stated in the derivation string), phase angle and illuminated fraction, and
the galactic centre (Sgr A*: RA 17h45m40.04s, Dec -29d00m28.1s, J2000) as a
fixed star. The core window is the intersection of three booleans - core
altitude > 5 deg, sun < -18 deg, moon below horizon - and is labelled
`geometric_core_window`: geometry only, no cloud, no transparency, no light
pollution, with `core_max_altitude_deg` served beside it so the low
culmination at 47.56 N (~10-15 deg) is visible rather than implied away.

### D4 - Interval evidence gets its own endpoint

Twilight bands and rise/set instants are intervals over the window, not
per-instant samples; forcing them through `/point`'s Provenance would claim
sampling semantics (cell distances, freshness ages) they do not have.
`GET /astronomy` returns the bands, the moon facts and one provenance block
(source `nasa-jpl-de442`, derivation "skyfield <version> + JPL DE442 (sha256
8d5001fa...)", `derivation_version: astronomy-de442-v1`, `operational:
false`). Same coordinate bounds rule as `/point` (422 outside the core
bounds) and 422 for a reference outside the window.

### D5 - Web: bands beside the coverage rows, cards in the conditions panel

Two band rows reuse the coverage-ribbon geometry (fractions of
windowStart..windowEnd): darkness (day/civil/nautical/astronomical as
opacity steps) and moon-above-horizon. Each band carries a text alternative
naming the interval times; an unavailable astronomy response renders the
rows' unavailable text, never an empty band pretending to be "no darkness".
The "Tonight" cards state darkness start/end, moonrise/set, phase +
illumination, and the core window with the mandatory geometry-only caption.
