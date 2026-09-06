"""Read the one window definition from the API package.

`evidence-window-timeline` requires the sliding window to be "defined in
exactly one place so those four cannot drift apart", and that place is
``api/weather_api/config.py``. ``ingest`` re-exports it here rather than
importing it in five modules, so there is one import site if the two packages
are ever laid out differently.

The file is loaded by path rather than as ``weather_api.config``, because
``weather_api/__init__.py`` imports the FastAPI app, which imports
``ingest.contract``, which imports this module: a plain package import is a
cycle. Loading the one module by path takes the definition without waking the
API. Where the file is not beside ``ingest`` - a worker image that has not
shipped it - the package import is tried, and failing that the import fails
loudly rather than falling back to a second copy of the offsets, which is the
drift this module exists to prevent.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "api" / "weather_api" / "config.py"


def _load_config() -> ModuleType:
    existing = sys.modules.get("weather_api.config")
    if existing is not None:
        return existing
    if _CONFIG_PATH.is_file():
        spec = importlib.util.spec_from_file_location("_astraeus_window_config", _CONFIG_PATH)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return importlib.import_module("weather_api.config")


_config = _load_config()

WINDOW_BACK: timedelta = _config.WINDOW_BACK
WINDOW_FORWARD: timedelta = _config.WINDOW_FORWARD
sliding_window = _config.sliding_window

__all__ = ["WINDOW_BACK", "WINDOW_FORWARD", "sliding_window", "window_bounds"]


def window_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Alias kept so ingest call sites read as bounds rather than a window."""
    return sliding_window(now)
