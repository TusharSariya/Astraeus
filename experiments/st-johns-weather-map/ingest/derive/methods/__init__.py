"""The interpolation methods the map can be switched between.

One method is one complete answer to "what should be drawn between two real
frames". Each declares how it derives its motion fields from a variable's
frame sequence, and how it composites two frames at a fraction ``t`` of the
interval - the second being the Python statement of what its shader does, so
the held-out harness scores every method by its own rule rather than by the
baseline's.

Every enabled method is derived and published each cycle, so the scores in
provenance come from the same held-out frames of the same cycle and are
directly comparable. The client picks one; a method the artifact does not
carry 404s into the crossfade fallback that is already disclosed.

Evidence rules. A method may decide HOW retrieved frames are warped and
mixed. Under carve-out (d) of the governing rule (owner decision
2026-09-01) a method may also draw a GENERATED value between two retrieved
frames - one in neither frame - but only when every one of these holds
together: it comes from a published, cited physical or statistical
construction and nothing fitted to the pictures it produces; it reads only
the same run's own retrieved fields and the layer's own frames; it is zero
at both real instants by construction; it is bounded to the variable's
physical range and a published cap; it is admitted per variable only on a
FIXED control (``harness.admit``: a plain crossfade and a plain advection
of the same frames, on mean error, structural similarity and sharpness),
with every score published; it is disclosed on the map as GENERATED and
named; it is switchable at three levels - ``enabled = False`` here,
``WEATHER_GENERATED_DISPLAY=off`` per deployment (``generated_display_enabled``,
honoured by ``enabled_methods``), and per reader in the menu - and it never
reaches a data path. Such a method sets ``generative = True``. Every method
here is endpoint-exact - at ``t = 0`` and ``t = 1`` the real frame shows
untouched - and that is a property tests pin, not a convention.

Retired constructions are absent, not disabled: six modules (intermediate
flow, visibility blend, scale cascade, flow net, full advection, development
residual) measured worse on fixed controls or were undrawable and were
deleted on 2026-09-01. Their measurements live in the research record and
in the docstrings of what replaced them, not in a registry entry.

**Adding a method.** Write one module in this package holding one subclass of
``InterpolationMethod``, then add it to ``METHODS`` below. Nothing else in
the codebase needs to change for a derive-side method: the derive loop finds
it through this registry, the artifact grows a slot on its ``method`` axis,
``/methods`` announces it and the menu offers it. A method that also needs a
new client construction adds a shader branch keyed by its ``shader`` name.

Dependency direction: ``flow_ops`` <- ``methods.contract`` <-
``methods.harness`` <- each method module <- this registry.
"""

from __future__ import annotations

import os
from typing import Any

from ingest.derive.methods.baseline import BaselineMethod
from ingest.derive.methods.companion import published_companion
from ingest.derive.methods.contract import (
    InterpolationMethod,
    MethodContext,
    PairMotion,
    Requirement,
)
from ingest.derive.methods.error_variance_blend import ErrorVarianceBlendMethod
from ingest.derive.methods.goes_transfer import GOESTransferMethod
from ingest.derive.methods.harness import (
    HELD_OUT_FRACTIONS,
    _interpolation_skill,
    _score_full,
    _score_one,
    admit,
    admit_reasons,
)
from ingest.derive.methods.height_steering import HeightSteeringMethod
from ingest.derive.methods.residual_advection import ResidualAdvectionMethod
from ingest.derive.methods.residual_generative import ResidualGenerativeMethod

#: Every method the bench knows, in menu order. `baseline` must stay first
#: and must stay enabled: it is the default the client falls back to and the
#: control every other method's score is read against.
METHODS: tuple[InterpolationMethod, ...] = (
    BaselineMethod(),
    ErrorVarianceBlendMethod(),
    ResidualAdvectionMethod(),
    # Menu order is load-bearing: the generative sibling sits directly under
    # the non-generative residual it extends, because it IS that construction
    # with its timing decided by the run's own physics and its strength
    # allowed past the bound that keeps the sibling inside the two retrieved
    # values. `enabled_methods` drops it when the deployment kill switch is
    # off; the reader's own default-off is enforced in the menu.
    ResidualGenerativeMethod(),
    HeightSteeringMethod(),
    GOESTransferMethod(),
)

DEFAULT_METHOD_ID = "baseline"

#: The deployment-level kill switch for generated display values. Read at
#: call time, never at import, so a test or an operator can flip it without
#: a restart of the module.
GENERATED_DISPLAY_ENV = "WEATHER_GENERATED_DISPLAY"


def generated_display_enabled() -> bool:
    """Is the deployment allowed to derive and offer GENERATED display values?

    ``WEATHER_GENERATED_DISPLAY`` set to ``off``, ``0``, ``false`` or ``no``
    (any case, surrounding whitespace ignored) refuses every generative
    method at derive time and is reported by ``/methods``. Unset, empty or
    anything else means enabled: the default is on because a construction
    that is never derived is never measured, and the reader's own default
    is enforced in the menu (generative entries are off by default there
    and never restored from a stored preference). This is the middle of the
    three switches carve-out (d) requires - per method ``enabled``, per
    deployment here, per reader in the menu.
    """
    value = os.environ.get(GENERATED_DISPLAY_ENV, "")
    return value.strip().lower() not in {"off", "0", "false", "no"}


def enabled_methods() -> tuple[InterpolationMethod, ...]:
    """The methods this cycle derives, baseline first.

    A generative method is excluded when the deployment kill switch is off,
    so a derive under ``WEATHER_GENERATED_DISPLAY=off`` publishes no
    generated field at all - not a zeroed one, none.
    """
    allow_generated = generated_display_enabled()
    return tuple(
        method for method in METHODS
        if method.enabled and (allow_generated or not method.generative)
    )


def method_by_id(method_id: str) -> InterpolationMethod | None:
    """The method with this wire name, or None - never a silent substitute."""
    return next((method for method in METHODS if method.id == method_id), None)


def method_catalogue() -> list[dict[str, Any]]:
    """The registry as plain data, for the API to serve and the menu to render.

    ``requirements`` is what makes a method honest in the menu rather than
    merely present: a method whose ingredient is missing from this deployment
    reduces to some other construction, and a reader who picks it and sees no
    change deserves to be told why rather than left to wonder whether the
    control did anything. ``plain``, ``gap`` and ``notes`` are the reader
    copy (one sentence to act on, one on what cannot be shown, and the
    science). ``generation_disabled`` is True on a generative entry while the
    deployment kill switch is off: the method is registered, but this
    deployment derives and offers nothing from it.
    """
    allow_generated = generated_display_enabled()
    return [
        {
            "id": method.id,
            "title": method.title,
            "summary": method.summary,
            "plain": method.plain,
            "gap": method.gap,
            "notes": method.notes,
            "shader": method.shader,
            "enabled": method.enabled,
            "generative": method.generative,
            "generation_disabled": bool(method.generative and not allow_generated),
            "requirements": [
                {"name": item.name, "met": bool(item.met), "detail": item.detail, "diagnostic": item.diagnostic}
                for item in method.requirements()
            ],
        }
        for method in METHODS
    ]


__all__ = [
    "DEFAULT_METHOD_ID",
    "GENERATED_DISPLAY_ENV",
    "HELD_OUT_FRACTIONS",
    "METHODS",
    "BaselineMethod",
    "ErrorVarianceBlendMethod",
    "GOESTransferMethod",
    "HeightSteeringMethod",
    "ResidualAdvectionMethod",
    "ResidualGenerativeMethod",
    "published_companion",
    "InterpolationMethod",
    "MethodContext",
    "PairMotion",
    "Requirement",
    "_interpolation_skill",
    "_score_full",
    "_score_one",
    "admit",
    "admit_reasons",
    "enabled_methods",
    "generated_display_enabled",
    "method_by_id",
    "method_catalogue",
]
