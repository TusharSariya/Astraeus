"""Adapter modules, imported for their registration side effects.

Families land independently, so a module that does not *exist* yet is not an
error: the worker runs with whatever adapters are present today.

A module that exists and fails is a different thing entirely, and it used to be
swallowed here. ``ingest.registry.register`` raises when two adapters claim the
same registry source id, and this loader caught that, logged it and carried on —
so an entire adapter family could vanish from the worker while every test still
passed and ``/sources/status`` reported nothing wrong. A silently skipped family
is the same class of dishonesty this experiment exists to remove, so a module
that is present and does not import now takes the process down.

The two cases are told apart by ``importlib.util.find_spec`` rather than by
catching ``ModuleNotFoundError``, because that exception is also what a *present*
module raises when its own imports are broken — the exact case that must be loud.
"""

from __future__ import annotations

import importlib
import importlib.util

_MODULES = (
    "eccc_datamart",
    "eccc_geomet",
    # The four ensemble access shapes, in the owner's declared build order:
    # REPS (per-member WCS coverages) here, then AIFS-ENS and IFS ENS in
    # ``ecmwf_opendata`` and GEFS in ``noaa_s3``, both listed below. Loading an
    # adapter never schedules its family: every one of them gates on
    # ``IngestConfig.ensemble.schedulable``, which the registry declares false
    # for all six families.
    "eccc_geomet_ensemble",
    "noaa_s3",
    "ecmwf_opendata",
    "dwd_icon",
    "awc",
    "eccc_ogc",
    "goes_abi",
    "swpc",
)


def _load() -> list[str]:
    loaded: list[str] = []
    for name in _MODULES:
        qualified = f"{__name__}.{name}"
        if importlib.util.find_spec(qualified) is None:
            # The family has not landed yet. Deliberately tolerated.
            continue
        # Anything that goes wrong from here on propagates, registration
        # collisions included.
        importlib.import_module(qualified)
        loaded.append(name)
    return loaded


LOADED = _load()
