"""Record the threshold overrides a score was produced under.

A profile declares a default for every threshold it names, and a reader may
move one: a runner who is happy in a stronger gust than the profile assumes,
an astronomer who wants a stricter cloud limit. The score that comes back
looks identical either way, which is exactly the problem. Two readers
comparing screenshots, or one reader comparing this evening with last, have no
way to tell a changed sky from a changed threshold unless the score says.

So every score carries an :class:`OverrideProvenance`. When an override was in
force it names the threshold, the profile's default and the reader's value.
When none was, it says so - ``no_override_in_force`` is ``True`` and the
record is still present. The record is never omitted, because an absent record
and "no override" would be indistinguishable, and a reader would have to
assume one of them.

An override naming a threshold the profile does not declare raises: it is a
stale interface, a renamed threshold or a typo, and applying it to nothing
while reporting a score would be the silent failure this whole module exists
to prevent.

Nothing here evaluates a threshold or produces a score. It records what the
evaluation was done under.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ThresholdOverride:
    """One threshold a reader moved, with the default it moved away from.

    Both numbers are kept. The reader's value alone would not let anybody see
    that the profile as published would have answered differently, which is
    the only reason to record an override at all.
    """

    threshold: str
    profile_default: float
    value: float

    @property
    def changes_the_default(self) -> bool:
        """Whether this override actually differs from the default.

        Reported, not used to filter: an override equal to the default is
        still an override in force, because the reader set it and a later
        change to the profile's default will not move it.
        """
        return self.value != self.profile_default

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "profile_default": self.profile_default,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class OverrideProvenance:
    """What a score says about the thresholds that produced it.

    ``no_override_in_force`` is redundant with ``overrides`` being empty, and
    it is carried anyway: the specification asks a score with no override to
    say so explicitly, and a consumer reading a serialised record should not
    have to infer a statement from the absence of a list.
    """

    profile_id: str
    profile_version: int
    overrides: list[ThresholdOverride]
    no_override_in_force: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "overrides": [item.as_dict() for item in self.overrides],
            "no_override_in_force": self.no_override_in_force,
        }


def record_overrides(
    profile: Mapping[str, Any], overrides: Mapping[str, float]
) -> OverrideProvenance:
    """The provenance record for a score produced under these overrides.

    ``profile`` is a parsed profile mapping (``id``, ``version``,
    ``thresholds``). Every name in ``overrides`` must be a threshold the
    profile declares, and that threshold must declare a default; otherwise
    :class:`ValueError` names it, because a score recorded against a
    threshold that does not exist records nothing.

    An empty ``overrides`` yields an empty list and
    ``no_override_in_force=True`` - a record, not an omission.
    """
    if not isinstance(profile, Mapping):
        raise TypeError(f"profile must be a mapping, got {type(profile).__name__}")
    profile_id = profile.get("id")
    version = profile.get("version")
    declared = profile.get("thresholds") or {}
    if not isinstance(declared, Mapping):
        raise TypeError(
            f"{profile_id}: thresholds must be a mapping, got {type(declared).__name__}"
        )

    recorded: list[ThresholdOverride] = []
    for name in sorted(overrides):
        spec = declared.get(name)
        if spec is None:
            raise ValueError(
                f"{profile_id}: {name}: no such threshold in this profile; the declared "
                f"thresholds are {', '.join(sorted(declared)) or 'none'}, and an override "
                "against an undeclared threshold would be recorded against nothing"
            )
        if not isinstance(spec, Mapping) or spec.get("default") is None:
            raise ValueError(
                f"{profile_id}: {name}: threshold declares no default, so an override has "
                "nothing to be recorded against"
            )
        recorded.append(
            ThresholdOverride(
                threshold=name,
                profile_default=spec["default"],
                value=overrides[name],
            )
        )

    return OverrideProvenance(
        profile_id=profile_id,
        profile_version=version,
        overrides=recorded,
        no_override_in_force=not recorded,
    )
