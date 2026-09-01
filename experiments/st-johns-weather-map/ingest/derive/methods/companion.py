"""Reaching a published artifact other than the one being derived.

A method may need another source's artifact - an observed cloud mask, an
observed cloud-top height. It comes through this hook rather than through
``MethodContext`` so the derive loop and the shared context stay untouched
whatever a method needs, and so a test can inject a fake with one
monkeypatch.

None means absent, and absent is a fact every caller must handle: a missing
companion costs that method its prior and never the motion artifact the whole
map depends on. Every failure path returns None rather than raising, and the
bytes are checked against their recorded digest exactly as the derive checks
the surface artifact - a companion that fails that check is not a companion.
"""

from __future__ import annotations

from typing import Any

def published_companion(source_id: str, logical_name: str, *, workdir: Any = None) -> Any | None:
    """Another published artifact, opened read-only, or None.

    A method may need an artifact other than the one being derived - an
    observed cloud mask, an observed cloud-top height. It is reached through
    this hook rather than through MethodContext so the derive loop and the
    shared context stay untouched across the bench, and so a test can inject
    a fake with one monkeypatch.

    None means absent, and absent is a fact every caller must handle: a
    missing companion costs that method its prior and never the motion
    artifact the whole map depends on. Every failure path returns None rather
    than raising, for that same reason.
    """
    import tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    try:
        from ingest.store import sha256_of, store_from_env  # noqa: PLC0415

        store = store_from_env()
        artifact = next(
            (item for item in store.current_artifacts(source_ids=[source_id])
             if item.logical_name == logical_name),
            None,
        )
        if artifact is None:
            return None
        target = Path(workdir or tempfile.mkdtemp()) / f"{source_id}-{logical_name}.zarr.zip"
        store.s3.download_file(store.config.bucket, artifact.object_key, str(target))
        expected = str(artifact.provenance.get("sha256", ""))
        if expected and sha256_of(target) != expected:
            # Bytes that do not match their recorded digest are not a
            # companion. Silence is safe here: the method loses its prior.
            return None
        import xarray  # noqa: PLC0415
        import zarr  # noqa: PLC0415

        return xarray.open_zarr(zarr.storage.ZipStore(str(target), mode="r"), consolidated=False)
    except Exception:
        return None
