"""Pinned JPL planetary ephemeris for Astraeus geometry.

Download belongs in scripts/fetch_ephemeris.py. API process startup MUST only
verify the local file and refuse to serve if it is missing or corrupt.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Spec-Refs: ECL26-GEO-001 — Skyfield with pinned DE442 (de442.bsp)
EPHEMERIS_ID = "DE442"
EPHEMERIS_FILENAME = "de442.bsp"
EPHEMERIS_URL = (
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de442.bsp"
)
EPHEMERIS_SHA256 = (
    "8d5001fab315eeff222cc51f7cf7ffcdb43fb38fb9ac73ff09e09a5b361fd388"
)

DATA_DIR = Path(__file__).resolve().parent / "data"
EPHEMERIS_PATH = DATA_DIR / EPHEMERIS_FILENAME


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_ephemeris(path: Path = EPHEMERIS_PATH) -> Path:
    """Return path if present and checksum matches; raise otherwise."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Pinned ephemeris missing: {path}. "
            "Run: uv run python scripts/fetch_ephemeris.py"
        )
    actual = sha256_file(path)
    if actual != EPHEMERIS_SHA256:
        raise ValueError(
            f"Ephemeris checksum mismatch for {path}: "
            f"expected {EPHEMERIS_SHA256}, got {actual}. "
            "Re-run: uv run python scripts/fetch_ephemeris.py"
        )
    return path
