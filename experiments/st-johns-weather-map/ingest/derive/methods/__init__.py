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

Evidence rules are unchanged by the bench: a method may decide HOW retrieved
frames are warped and mixed, never invent content that was not retrieved.
Every method here is endpoint-exact - at ``t = 0`` and ``t = 1`` the real
frame shows untouched - and that is a property tests pin, not a convention.

**Adding a method.** Write one module in this package holding one subclass of
``InterpolationMethod``, then add it to ``METHODS`` below. Nothing else in
the codebase needs to change for a derive-side method: the derive loop finds
it through this registry, the artifact grows a slot on its ``method`` axis,
``/methods`` announces it and the menu offers it. A method that also needs a
new client construction adds a shader branch keyed by its ``shader`` name.
This layout replaced a single module in which every method's class sat in one
file - six methods written in parallel all appended to the same tuple in the
same file, and merging that was the whole cost.

Dependency direction: ``flow_ops`` <- ``methods.contract`` <-
``methods.harness`` <- each method module <- this registry.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.methods.baseline import BaselineMethod
from ingest.derive.methods.companion import published_companion
from ingest.derive.methods.development_residual import DevelopmentResidualMethod
from ingest.derive.methods.flow_net import FlowNetMethod
from ingest.derive.methods.goes_transfer import GOESTransferMethod
from ingest.derive.methods.height_steering import HeightSteeringMethod
from ingest.derive.methods.contract import (
    InterpolationMethod,
    MethodContext,
    PairMotion,
    Requirement,
)
from ingest.derive.methods.harness import (
    HELD_OUT_FRACTIONS,
    _interpolation_skill,
    _score_one,
)
from ingest.derive.methods.intermediate_flow import IntermediateFlowMethod
from ingest.derive.methods.scale_cascade import ScaleCascadeMethod
from ingest.derive.methods.visibility_blend import VisibilityBlendMethod

#: Every method the bench knows, in menu order. `baseline` must stay first
#: and must stay enabled: it is the default the client falls back to and the
#: control every other method's score is read against.
METHODS: tuple[InterpolationMethod, ...] = (
    BaselineMethod(),
    IntermediateFlowMethod(),
    VisibilityBlendMethod(),
    ScaleCascadeMethod(),
    HeightSteeringMethod(),
    DevelopmentResidualMethod(),
    GOESTransferMethod(),
    FlowNetMethod(),
)

DEFAULT_METHOD_ID = "baseline"


def enabled_methods() -> tuple[InterpolationMethod, ...]:
    """The methods this cycle derives, baseline first."""
    return tuple(method for method in METHODS if method.enabled)


def method_by_id(method_id: str) -> InterpolationMethod | None:
    """The method with this wire name, or None - never a silent substitute."""
    return next((method for method in METHODS if method.id == method_id), None)


def method_catalogue() -> list[dict[str, Any]]:
    """The registry as plain data, for the API to serve and the menu to render.

    ``requirements`` is what makes a method honest in the menu rather than
    merely present: a method whose ingredient is missing from this deployment
    reduces to some other construction, and a reader who picks it and sees no
    change deserves to be told why rather than left to wonder whether the
    control did anything.
    """
    return [
        {
            "id": method.id,
            "title": method.title,
            "summary": method.summary,
            "shader": method.shader,
            "enabled": method.enabled,
            "generative": method.generative,
            "requirements": [
                {"name": item.name, "met": bool(item.met), "detail": item.detail}
                for item in method.requirements()
            ],
        }
        for method in METHODS
    ]


__all__ = [
    "DEFAULT_METHOD_ID",
    "HELD_OUT_FRACTIONS",
    "METHODS",
    "BaselineMethod",
    "IntermediateFlowMethod",
    "DevelopmentResidualMethod",
    "FlowNetMethod",
    "GOESTransferMethod",
    "HeightSteeringMethod",
    "ScaleCascadeMethod",
    "VisibilityBlendMethod",
    "published_companion",
    "InterpolationMethod",
    "MethodContext",
    "PairMotion",
    "Requirement",
    "_interpolation_skill",
    "_score_one",
    "enabled_methods",
    "method_by_id",
    "method_catalogue",
]
