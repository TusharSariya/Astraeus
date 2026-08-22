#!/usr/bin/env python3
"""Fetch the pinned JPL ephemeris when missing or checksum-invalid.

Usage (from v1/services/api):

    uv run python scripts/fetch_ephemeris.py
    uv run python scripts/fetch_ephemeris.py --force

Do not call this from API request handlers. Production images should bake or
mount the verified file; this script is for local/CI bootstrap only.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# Allow `uv run python scripts/fetch_ephemeris.py` from the api directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ephemeris import (  # noqa: E402
    DATA_DIR,
    EPHEMERIS_PATH,
    EPHEMERIS_SHA256,
    EPHEMERIS_URL,
    sha256_file,
    verify_ephemeris,
)


def _status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    actual = sha256_file(path)
    if actual == EPHEMERIS_SHA256:
        return "ok"
    return "mismatch"


def fetch(force: bool = False) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = _status(EPHEMERIS_PATH)
    if status == "ok" and not force:
        print(f"ephemeris ok: {EPHEMERIS_PATH}")
        print(f"sha256: {EPHEMERIS_SHA256}")
        return EPHEMERIS_PATH

    if status == "mismatch":
        print(f"checksum mismatch; re-downloading {EPHEMERIS_PATH.name}")
    elif force:
        print(f"force re-download of {EPHEMERIS_PATH.name}")
    else:
        print(f"missing; downloading {EPHEMERIS_PATH.name}")

    print(f"url: {EPHEMERIS_URL}")
    try:
        with urllib.request.urlopen(EPHEMERIS_URL, timeout=120) as response:
            with tempfile.NamedTemporaryFile(
                dir=DATA_DIR, prefix=".de442.", suffix=".partial", delete=False
            ) as partial:
                partial_path = Path(partial.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    partial.write(chunk)
    except urllib.error.URLError as exc:
        raise SystemExit(f"download failed: {exc}") from exc

    actual = sha256_file(partial_path)
    if actual != EPHEMERIS_SHA256:
        partial_path.unlink(missing_ok=True)
        raise SystemExit(
            f"downloaded file failed checksum: expected {EPHEMERIS_SHA256}, "
            f"got {actual}"
        )

    partial_path.replace(EPHEMERIS_PATH)
    verify_ephemeris(EPHEMERIS_PATH)
    print(f"wrote {EPHEMERIS_PATH}")
    print(f"sha256: {actual}")
    return EPHEMERIS_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when the local file already matches",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify only; exit 1 if missing or mismatched",
    )
    args = parser.parse_args()
    if args.check:
        try:
            verify_ephemeris()
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"ephemeris ok: {EPHEMERIS_PATH}")
        return
    fetch(force=args.force)


if __name__ == "__main__":
    main()
