#!/usr/bin/env python3
"""Replay ticket 153's retained normalized artifacts through the real API."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy
import xarray
import zarr
from fastapi.testclient import TestClient

from ingest.captures.sst_analysis import OISST_MANIFEST, OSTIA_MANIFEST
from ingest.manifest import validate_run
from ingest.store import CurrentArtifact
from weather_api.store import LiveStore

UTC = timezone.utc
ROOT = Path(os.environ.get("WEATHER_SST_REPLAY_ROOT", "/tmp/astraeus-sst-153"))


class ReplayStore(LiveStore):
    def __init__(self, pairs):
        super().__init__(artifact_store=None, cache_dir=ROOT / "cache")
        self.pairs = pairs

    def assert_object_store_reachable(self) -> None:
        pass

    def current(self):
        return [artifact for artifact, _dataset in self.pairs]

    def _local_copy(self, artifact):
        path = Path(artifact.object_key)
        payload = path.read_bytes()
        self._verify(artifact, len(payload), hashlib.sha256(payload).hexdigest())
        return path


def main() -> None:
    definitions = (
        ("metoffice-ostia-sst", "metoffice-ostia-sst.zarr.zip", "ostia-20260904-0330fdaa1bd4c67d", datetime(2026, 9, 4, tzinfo=UTC), datetime(2026, 9, 6, 0, 15, 17, 751851, tzinfo=UTC), "ostia-20260904", "0.05 degree", "ostia-timechunked-v1", {"sea_surface_temperature": "kelvin", "sea_surface_temperature_uncertainty": "kelvin", "sea_surface_temperature_mask": "native bit mask"}),
        ("noaa-oisst-v2-1", "noaa-oisst-v2-1.zarr.zip", "oisst-20260904-preliminary-536d1ecdbb3b522c", datetime(2026, 9, 4, 12, tzinfo=UTC), datetime(2026, 9, 6, 0, 15, 20, 11383, tzinfo=UTC), "oisst-20260904-preliminary", "0.25 degree", "oisst-v2r01-v1", {"sea_surface_temperature": "Celsius", "sea_surface_temperature_uncertainty": "Celsius"}),
    )
    pairs = []
    for index, (source_id, filename, revision, valid_time, captured, provider_run_id, resolution, adapter_version, original_units) in enumerate(definitions):
        path = ROOT / source_id / filename
        with zarr.storage.ZipStore(path, mode="r") as store:
            dataset = xarray.open_zarr(store, consolidated=False).load()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = OSTIA_MANIFEST if index == 0 else OISST_MANIFEST
        replay_window = type("Window", (), {"start": valid_time - timedelta(hours=24), "end": valid_time + timedelta(hours=24)})()
        verdict = validate_run(manifest, dataset, window=replay_window)
        provenance = {
            "adapter_version": adapter_version,
            "artifact_revision": revision,
            "native_resolution": resolution,
            "native_crs": "EPSG:4326",
            "quality": {**verdict.as_quality(), "detail": verdict.detail + "; reconstructed from retained normalized bytes, structural validation only"},
            "coverage": verdict.as_coverage(),
            **manifest.as_manifest_block(),
            "original_units": original_units,
            "sha256": digest,
        }
        artifact = CurrentArtifact(source_id, "sst_analysis", revision, str(path), "application/zarr+zip", path.stat().st_size, provenance, captured, valid_time, captured, provider_run_id, "EPSG:4326")
        pairs.append((artifact, dataset))

    ostia = pairs[0][1]
    lats, lons = numpy.asarray(ostia.latitude), numpy.asarray(ostia.longitude)
    eligible = numpy.isfinite(ostia.sea_surface_temperature.values[0]) & (lats[:, None] >= 46.5) & (lats[:, None] <= 48.5) & (lons[None, :] >= -55) & (lons[None, :] <= -51)
    y, x = numpy.argwhere(eligible)[len(numpy.argwhere(eligible)) // 2]
    latitude, longitude = float(lats[y]), float(lons[x])

    api = importlib.import_module("weather_api.app")
    api.live_store = lambda: ReplayStore(pairs)
    client = TestClient(api.app)
    output = []
    for artifact, dataset in pairs:
        stamp = numpy.asarray(dataset.valid_time.values)[0].astype("datetime64[s]").astype(object).replace(tzinfo=UTC)
        api.now = lambda moment=stamp: moment + timedelta(hours=12)
        response = client.get(f"{api.PREFIX}/point", params={"latitude": latitude, "longitude": longitude, "valid_time": stamp.isoformat()})
        body = response.json()
        fields = {field["field"]: field for field in body["fields"] if field["provenance"]["source_id"] == artifact.source_id}
        located = dataset.sel(latitude=latitude, longitude=longitude, valid_time=numpy.datetime64(stamp.replace(tzinfo=None), "ns"), method="nearest")
        for name in dataset.data_vars:
            expected = float(located[name].values)
            actual = fields[name]
            assert numpy.isclose(actual["value"], expected, equal_nan=True)
            assert actual["provenance"]["normalized_units"] == dataset[name].attrs["units"]
            assert actual["provenance"]["valid_time"] == stamp.isoformat().replace("+00:00", "Z")
            assert actual["provenance"]["artifact_revision"] == artifact.revision_id
        output.append({"source_id": artifact.source_id, "status": response.status_code, "body": body})
    print(json.dumps({"point": [latitude, longitude], "responses": output}, indent=2, default=str))


if __name__ == "__main__":
    main()
