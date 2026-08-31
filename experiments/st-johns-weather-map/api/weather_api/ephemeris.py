"""Pinned JPL planetary ephemeris for the astronomy capability.

Recovered from the earlier v1 tree (commit 5a743a8) with the same rule:
download belongs in ``scripts/fetch_ephemeris.py``; the API process only
verifies the local file and refuses the astronomy capability if it is
missing or corrupt. Verification runs once per process and is cached - a
114 MB sha256 per request would be a denial of service against ourselves.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

EPHEMERIS_ID = "DE442"
EPHEMERIS_FILENAME = "de442.bsp"
EPHEMERIS_URL = (
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de442.bsp"
)
EPHEMERIS_SHA256 = (
    "8d5001fab315eeff222cc51f7cf7ffcdb43fb38fb9ac73ff09e09a5b361fd388"
)
#: NAIF Content-Length observed at pin time; the live smoke test checks it.
EPHEMERIS_BYTES = 119771136

#: Default: the experiment-level data directory, overridable for containers.
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ephemeris" / EPHEMERIS_FILENAME


def ephemeris_path() -> Path:
    return Path(os.environ.get("WEATHER_EPHEMERIS_PATH", str(_DEFAULT_PATH)))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_ephemeris(path: Path | None = None) -> Path:
    """Return the path if present and checksum-matched; raise otherwise."""
    resolved = path if path is not None else ephemeris_path()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Pinned ephemeris missing: {resolved}. "
            "Run: uv run python scripts/fetch_ephemeris.py"
        )
    actual = sha256_file(resolved)
    if actual != EPHEMERIS_SHA256:
        raise ValueError(
            f"Ephemeris checksum mismatch for {resolved}: "
            f"expected {EPHEMERIS_SHA256}, got {actual}. "
            "Re-run: uv run python scripts/fetch_ephemeris.py"
        )
    return resolved
