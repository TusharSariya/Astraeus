from __future__ import annotations

from dataclasses import dataclass


LOCAL_STORAGE_CAP_BYTES = 25 * 1024**3


@dataclass(frozen=True)
class ArtifactRevision:
    revision: str
    size_bytes: int
    complete: bool
    qc_passed: bool


class FixtureArtifactStore:
    """Models atomic visibility and the local hard cap without filesystem I/O."""

    def __init__(self, cap_bytes: int = LOCAL_STORAGE_CAP_BYTES) -> None:
        if cap_bytes <= 0:
            raise ValueError("storage cap must be positive")
        self.cap_bytes = cap_bytes
        self.visible: dict[str, ArtifactRevision] = {}
        self.staged: dict[str, ArtifactRevision] = {}

    @property
    def used_bytes(self) -> int:
        return sum(item.size_bytes for item in self.visible.values()) + sum(item.size_bytes for item in self.staged.values())

    def stage(self, product: str, artifact: ArtifactRevision) -> None:
        replaced = self.staged.get(product)
        projected = self.used_bytes - (replaced.size_bytes if replaced else 0) + artifact.size_bytes
        if projected > self.cap_bytes:
            raise ValueError("25 GiB local storage cap would be exceeded")
        self.staged[product] = artifact

    def publish(self, product: str) -> ArtifactRevision:
        artifact = self.staged.get(product)
        if artifact is None:
            raise KeyError(product)
        if not artifact.complete or not artifact.qc_passed:
            raise ValueError("artifact must be complete and pass QC before publication")
        previous = self.visible.get(product)
        projected = self.used_bytes - artifact.size_bytes - (previous.size_bytes if previous else 0) + artifact.size_bytes
        if projected > self.cap_bytes:
            raise ValueError("25 GiB local storage cap would be exceeded")
        self.visible[product] = artifact
        del self.staged[product]
        return artifact

    def restart(self) -> None:
        """Discard incomplete staging, preserving the last atomically visible run."""
        self.staged.clear()


def probe_normalized_array(values: list[list[float]], row: int, column: int) -> float:
    if row < 0 or column < 0:
        raise IndexError("probe indexes must be non-negative")
    return values[row][column]
