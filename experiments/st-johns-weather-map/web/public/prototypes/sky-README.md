# Sky view design study

**Experiment. A / Horizon instrument selected.** The owner chose “i like A”
on September 5, 2026 UTC. Three original alternatives remain inside the settled Bench
shell, for [Design the Sky view](https://github.com/TusharSariya/Astraeus/issues/51).
This route is a standalone throwaway HTML study beside the prior Series study;
no production route or specification is changed.

Run from this directory:

```sh
PORT=5200 python3 serve.py
```

Open <http://localhost:5200/sky.html?variant=A>. The server’s console prints the
older provenance route; use the Sky URL above. Its `/api` proxy reads localhost:8000.

- **A / Horizon instrument:** orientation first. Registered horizon and fraction
  gauges occupy the main column; geometry and evidence sit alongside.
- **B / Night planner:** time first. Darkness, moon-above-horizon and geometric
  core windows lead, followed by planetary series and point evidence.
- **C / Evidence ledger:** source and absence first. A category index leads through
  celestial, atmospheric, planetary and site evidence in labelled ledger lanes.

Use the bottom arrows or left/right keys to switch. Arrow keys are not intercepted
inside native controls. The shared instant, location and inspector selection survive
layout changes. Variant, Focus and theme are reload-stable in the URL; live results,
selected disclosure and display simulation state live only in memory.

## Review controls

- **Location:** Signal Hill uses its copied registered horizon; the arbitrary
  St. John’s point uses separately retrieved responses and has no site horizon.
- **Shared instant:** five retrieved requests over 24 hours, including returned
  0% cloud at 00Z and unavailable cloud at 06Z. Rail marks use elapsed time.
- **Evidence:** saved historical capture (default), read-only live API, or an
  explicitly labelled unavailable state with no synthetic numeric values.
- **Read this Focus now:** reads astronomy, point and space weather independently.
  A failure is unavailable, never a fallback to saved capture. Choose saved
  capture explicitly to return to it. Requests time out after 20 seconds.
- **Theme / Vision:** settled C Hyperlegible tokens; light, dark, red night;
  grayscale and deuteranopia display simulations. This is not the outdoor test.
- **Evidence rows / inspection buttons:** open the docked inspector with the
  complete response, request, timestamps, quality, freshness and method.

The shell’s other view labels are context only. Navigation to other production
views and their shared store is outside this throwaway study. The switcher exists
only in this isolated static prototype directory; it is not mounted in the app.

## What the design does not imply

No Sun, Moon or galactic-core azimuth is served. Altitudes are read out but no
celestial body is placed on the dome. The horizon plot draws only registered
bearings/elevations, without applying them to the API’s geometric intervals.

Cloud-layer fractions are scalar gauges beside the dome, not a spatial cloud
reconstruction. Gauges neither sum the layers nor derive a new total. The
geometric total is a separate returned field. No seeing, transparency or local
aurora verdict is derived from weather or Kp.

No camera image was fetched. The registered sky camera is partnership-only,
without position or orientation, and is not associated with either Focus.

All numeric weather/astronomy/space values come from captured or live responses.
Registry context is a copied primary-source record from this branch, labelled as
such. No constructed numerical evidence is used. See
[sky-data-notes.md](sky-data-notes.md) for gaps and request evidence.

## Governance and verification

Classification: **Experiment**. No normative requirement status or production
conformance is asserted. `Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004,
GOV-SPEC-005`. These are governance constraints, not accepted Sky behavior.
Production implementation waits for the map’s API and specification handoff gates.

The existing experiment astronomy and space-weather contracts guide evidence
handling; they do not accept this new UI. In particular, unavailable astronomy
suppresses the response’s numeric placeholders and observed/outlook Kp remain
separate with their original per-reading statuses.

Verification is recorded in the issue progress comment and handoff. This
prototype has no added test suite. The owner selected A / Horizon instrument. B and C remain archived design
alternatives. This decision does not promote the prototype or accept production
specifications; API and specification handoff gates still apply.
