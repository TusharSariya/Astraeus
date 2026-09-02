"""The bench contract: what a method is, and what it is handed.

Everything here is shared by every method module in this package. It knows
nothing about any particular method, so a new plugin imports from here and
from ``flow_ops`` and needs nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class MethodContext:
    """Everything a method may read for one variable of one artifact.

    ``frames`` are the variable's published frames in time order, as percent
    fields that may contain NaN. ``indices`` are those frames' positions in
    the artifact's own time axis, which is what a method needs to look up
    another variable (a steering wind, a vertical velocity) at the same
    instants - the held-out harness passes a subsequence, so a method must
    never assume ``indices == range(len(frames))``.
    """

    variable: str
    frames: list[Any]
    indices: tuple[int, ...]
    interval_seconds: float
    dataset: Any = None
    #: Scratch shared by everything that reads this context: the harness
    #: memoises its fixed advection control per ``(first, last)`` frame pair
    #: here, and the baseline memoises its raw DIS flow per pair, so a method
    #: with several options to settle (the residual's gain, the generative
    #: sibling's timing switches) scores each of them without paying for the
    #: same optical flow again. Keyed by the artifact's own frame indices, so
    #: the harness's pair sub-contexts and the derive's full context share
    #: one cache safely. Excluded from equality: two contexts over the same
    #: frames are the same context whatever has been memoised so far.
    cache: dict = field(default_factory=dict, compare=False)


@dataclass
class PairMotion:
    """One adjacent pair's derived fields, in grid cells per frame interval.

    ``flow01`` is what the client warps along; ``confidence`` is the raw
    forward-backward agreement, ``support`` the trusted density behind the
    fill, and ``advect_weight`` the weight the display mixes advection
    against a crossfade on. ``extra`` carries whatever else a method needs
    the client to have, keyed by the field suffix it is stored under.
    """

    flow01: Any
    flow10: Any
    confidence: Any
    support: Any
    advect_weight: Any
    extra: dict[str, Any] = field(default_factory=dict)
    #: Scalars for provenance - how much of the field an optional ingredient
    #: actually reached, and anything else worth being able to check later.
    diagnostics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Requirement:
    """One thing a method needs before it can differ from the baseline.

    A method whose ingredient this deployment does not have is not broken -
    it reduces to some other construction, correctly and by design. But a
    reader who selects it and sees the picture not change is owed the reason,
    because a control that appears to do something must do it. Requirements
    are reported through /methods and shown in the menu.
    """

    name: str
    met: bool
    detail: str = ""
    #: Name of the per-method provenance diagnostic that actually answers this
    #: requirement, when one does.
    #:
    #: Some ingredients cannot be checked here at all. `requirements()` is a
    #: method-level call with no variable and no dataset, and the answer for
    #: omega is genuinely per variable - it lives in the surface artifact being
    #: derived, at the level that variable steers on. Hardcoding `met=False`
    #: to express "cannot know" told the menu the ingredient was MISSING, which
    #: for omega was simply untrue: it has been ingested all along, read
    #: correctly, and switched off by its own held-out gate instead. Naming the
    #: diagnostic lets the reader be told what the last derive actually found,
    #: rather than a placeholder that reads as a verdict.
    diagnostic: str = ""


class InterpolationMethod:
    """Base class: subclass, set the identity fields, override the two hooks.

    ``id`` is the wire name (``/flow?method=...``), stable forever once
    published. ``shader`` names the client construction this method's fields
    are meant for, so one shader can serve several derive-side methods.
    """

    id: str = "baseline"
    title: str = "Baseline"
    summary: str = ""
    #: Reader-facing copy, served beside ``summary`` by ``/methods``. ``plain``
    #: is one sentence a non-specialist can act on; ``gap`` is one sentence
    #: on what the method cannot show; ``notes`` is the science - the cited
    #: constructions and the measured decisions - rendered collapsed under
    #: the plain copy. Empty strings mean the API serves nothing for them.
    plain: str = ""
    gap: str = ""
    notes: str = ""
    #: Client construction: 'linear' | 'hermite' | one a method adds.
    shader: str = "hermite"
    #: Extra stored field suffixes, beyond the ones every method publishes.
    extra_suffixes: tuple[str, ...] = ()
    #: Of those, the ones that must be ZEROED when a pair or a variable is
    #: vetoed, alongside `advect_weight`.
    #:
    #: A method whose contribution is fenced by `advect_weight` needs nothing
    #: here - zeroing the weight already silences it. A method fenced by
    #: `1 - advect_weight`, which is the natural fence for anything that acts
    #: where advection FAILED, has the opposite polarity: zeroing the weight
    #: would turn its contribution up to maximum on exactly the pairs the
    #: derive just judged unfit to advect. Naming those suffixes here is what
    #: makes "published with zero weight" mean the same thing for them.
    vetoed_suffixes: tuple[str, ...] = ()
    #: False keeps a method in the registry but out of every cycle.
    enabled: bool = True
    #: True where the disclosure must say the pixels were generated rather
    #: than retrieved. No such method may ship without a carve-out amendment.
    generative: bool = False

    def requirements(self) -> list[Requirement]:
        """What this method needs in order to differ from the baseline.

        Checked when asked, not at import: an artifact published by a later
        cycle can satisfy a requirement this one does not. An empty list
        means the method always works with what it is handed.
        """
        return []

    def configure(self, context: MethodContext) -> tuple["InterpolationMethod", dict[str, Any]]:
        """Settle this variable's options by measurement, before deriving it.

        A method with an optional ingredient (a model wind, a terrain mask, a
        second source) decides here whether that ingredient earns its place -
        by scoring the held-out reconstruction with it and without it - and
        returns the configured method plus notes for provenance, so the claim
        is checkable rather than asserted. Returning ``self`` and ``{}`` is
        the right answer for a method with nothing to decide.

        Notes may carry ``"skill"``: the derive reuses it rather than paying
        for the same optical flow twice.
        """
        return self, {}

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """One PairMotion per adjacent frame pair. Never fewer, never more."""
        raise NotImplementedError

    def composite(self, previous: Any, following: Any, motion: PairMotion, t: float) -> Any:
        """What the client draws at ``t`` in [0, 1] - the shader, in Python.

        Endpoint exactness is required of every override: ``t = 0`` must
        return ``previous`` and ``t = 1`` must return ``following``, both
        untouched. The harness scores this function, so a composite that
        drifts from its shader silently mis-ranks its own method.
        """
        raise NotImplementedError
