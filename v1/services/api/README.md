# Astraeus API

FastAPI service for Astraeus V1 authoritative computation: observation geometry,
evidence normalization, scoring, and recommendations. Clients render results;
they do not recompute science.

This package is early. Today it boots FastAPI, verifies the pinned JPL
ephemeris, and exposes a health root. Eclipse local-circumstances come next.

Owning specs: [RFC-000](../../../docs/specv1/rfcs/RFC-000-SYSTEM-OVERVIEW.md),
[ECL26-GEO-001](../../../docs/specv1/features/eclipse-2026-08-12/SCIENCE_SPEC.md#ecl26-geo-001--calculate-local-circumstances-per-candidate).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python **3.13+** (project pin; toolchain target is 3.14 when the environment allows)
- Network once, to fetch `de442.bsp` from NAIF if it is not already present

## Setup

```bash
cd v1/services/api
uv sync
uv run python scripts/fetch_ephemeris.py
```

`fetch_ephemeris.py` downloads `data/de442.bsp` only when the file is missing
or its SHA-256 does not match the pin in `ephemeris.py`. It never runs as part
of an HTTP request.

```bash
# Verify only (CI / preflight)
uv run python scripts/fetch_ephemeris.py --check

# Force re-download
uv run python scripts/fetch_ephemeris.py --force
```

Ephemeris binaries are gitignored (`*.bsp`). Commit the pin and checksum, not
the 114 MB kernel.

## Run

```bash
uv run uvicorn main:app --reload
```

- App: http://127.0.0.1:8000/
- OpenAPI: http://127.0.0.1:8000/docs

Startup **verifies** the local ephemeris and refuses to boot if it is missing
or corrupt. Startup does **not** download from NAIF.

## Layout

```text
v1/services/api/
  main.py                 FastAPI app
  ephemeris.py            Pinned DE442 path, URL, SHA-256, verify helper
  scripts/fetch_ephemeris.py
  data/                   Local kernels (de442.bsp gitignored)
  pyproject.toml
```

## Tests

```bash
uv run pytest
```

No product tests yet. Add geometry regressions against the St. John's
2026-08-12 controls in the eclipse feature index when implementing
`ECL26-GEO-001`.

## Related docs

- [V1 specification index](../../../docs/specv1/README.md)
- [Governance](../../../docs/specv1/GOVERNANCE.md)
- [Contributing](../../../CONTRIBUTING.md)
- [NAIF planetary kernels](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/)
