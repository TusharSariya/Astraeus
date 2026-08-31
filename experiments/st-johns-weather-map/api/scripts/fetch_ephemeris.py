#!/usr/bin/env python3
"""Fetch the pinned JPL ephemeris when missing or checksum-invalid.

Usage (from api/):

    uv run python scripts/fetch_ephemeris.py            # fetch if needed
    uv run python scripts/fetch_ephemeris.py --check    # verify only
    uv run python scripts/fetch_ephemeris.py --force    # re-download

Do not call this from API request handlers. Production images mount the
verified file read-only; this script is for local/CI bootstrap only.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weather_api.ephemeris import (  # noqa: E402
    EPHEMERIS_SHA256,
    EPHEMERIS_URL,
    ephemeris_path,
    sha256_file,
    verify_ephemeris,
)


def _status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    if sha256_file(path) == EPHEMERIS_SHA256:
        return "ok"
    return "mismatch"


def fetch(force: bool = False) -> Path:
    destination = ephemeris_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    status = _status(destination)
    if status == "ok" and not force:
        print(f"ephemeris ok: {destination}")
        return destination

    print(f"{status}; downloading {destination.name}")
    print(f"url: {EPHEMERIS_URL}")
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            with urllib.request.urlopen(EPHEMERIS_URL) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
    except urllib.error.URLError as error:
        raise SystemExit(f"download failed: {error}") from error

    actual = sha256_file(temp_path)
    if actual != EPHEMERIS_SHA256:
        temp_path.unlink(missing_ok=True)
        raise SystemExit(
            f"downloaded file hashes to {actual}, not the pinned {EPHEMERIS_SHA256}; refusing to install it"
        )
    temp_path.replace(destination)
    print(f"installed {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only; exit nonzero when absent or mismatched")
    parser.add_argument("--force", action="store_true", help="re-download even when the checksum matches")
    args = parser.parse_args()
    if args.check:
        try:
            path = verify_ephemeris()
        except (FileNotFoundError, ValueError) as error:
            print(str(error))
            return 1
        print(f"ephemeris ok: {path}")
        return 0
    fetch(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
