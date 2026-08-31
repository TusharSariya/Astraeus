## Why

The map's night-sky audience needs one question answered before any cloud
layer matters: when is it actually dark? Twilight phases, the moon's rise,
set, phase and illumination, and the narrow windows when the Milky Way core
is up during astronomical darkness are pure geometry - computable to high
accuracy from a pinned JPL planetary ephemeris, with no provider feed, no
cadence and no staleness. This repository already pinned exactly that once:
commit 5a743a8 carried a checksum-verified DE442 kernel with an out-of-band
fetch script and a verify-only startup rule; the tree it lived in was later
removed, and no astronomical computation exists in the current code.

What is verified: the prior pin (URL and sha256 for de442.bsp) is recovered
from git history; NAIF serves the file today (checked 2026-08-30). What is
computed, not retrieved: every value this change serves derives from that one
retrieved, checksum-verified artifact plus published constants (Sgr A*
coordinates, standard twilight altitudes), and every response says so in its
derivation strings.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **Pinned kernel plumbing**: `api/weather_api/ephemeris.py` (recovered) pins
  the DE442 URL and sha256 and verifies the local file; download stays in
  `scripts/fetch_ephemeris.py`, never in a request handler or at boot. The
  kernel is mounted read-only into the api container only
  (`./data/ephemeris:/data/ephemeris:ro`, `WEATHER_EPHEMERIS_PATH`); the
  worker gets neither the mount nor the skyfield dependency. A missing or
  checksum-mismatched kernel makes the astronomy capability alone answer
  unavailable with the reason; the rest of the API is untouched.
- **`api/weather_api/astronomy.py`**: Skyfield + DE442 computations over the
  evidence window at the requested coordinate: sun altitude crossings at
  -0.833/-6/-12/-18 degrees (day/civil/nautical/astronomical bands), moon
  rise/set/altitude, phase and illuminated fraction, and the galactic-centre
  geometric window (core altitude above 5 degrees, sun below -18, moon below
  the horizon) with the core's maximum altitude stated.
- **`GET /astronomy`**: the bands and moon facts for the -3 h/+24 h window,
  one provenance block naming skyfield version, kernel id and sha256, 422
  outside the window, `operational: false`. Interval values live here, not in
  `/point`.
- **Registry**: `nasa-jpl-de442` registered (status `implementing`, anonymous
  HTTPS, cadence "static kernel; pinned release" - deliberately unparseable
  so the worker never schedules it).
- **Web**: a darkness band and a moon-above-horizon band beside the timeline
  coverage rows (same window fraction math, with text alternatives), and a
  "Tonight" group of metric cards (darkness start/end, moonrise/set, phase and
  illumination, core window with its geometry-only caption).

## Capabilities

### New Capabilities

- `astronomy-evidence`: values computed from the pinned, checksum-verified
  ephemeris - the honesty rules for serving computed geometry: verified
  kernel or nothing, disclosed derivation, no blending with weather evidence.

### Modified Capabilities

- `source-registry-catalogue`: a pinned static dataset is a registrable
  source whose cadence prose deliberately does not parse to a schedule.
- `web-evidence-interface`: timeline bands for computed astronomical
  intervals, with text alternatives and gaps shown as gaps.
