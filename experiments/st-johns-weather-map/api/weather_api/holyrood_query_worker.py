"""Bounded structural GIF validation; no palette or numerical interpretation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Execute this leaf without importing the scientific API package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ingest.experimental.holyrood_radar import MAX_IMAGE_BYTES, _gif_metadata

if __name__ == "__main__":
    body = sys.stdin.buffer.read(MAX_IMAGE_BYTES + 1)
    if len(body) > MAX_IMAGE_BYTES:
        raise ValueError("image byte ceiling exceeded")
    sys.stdout.write(json.dumps(_gif_metadata(body)))
