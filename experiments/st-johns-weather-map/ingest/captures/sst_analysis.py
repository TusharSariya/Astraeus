"""Isolated current OSTIA and NOAA OISST Level-4 SST capture harnesses.

Both products are evidence inputs only.  This adapter preserves the producer's
analysis identity, uncertainty, native grid and masks; it makes no fog claim.
"""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray
from numcodecs import get_codec

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr
from ingest.http import PoliteClient, parse_directory_listing
from ingest.manifest import RequiredField, RunManifest, validate_run

UTC = timezone.utc
EVIDENCE_BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}
OSTIA_ROOT = "https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001/METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2/timeChunked.zarr"
OISST_ROOT = "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_OISST_BYTES = 32 * 1024 * 1024
MAX_OSTIA_CHUNKS_PER_FIELD = 16

OSTIA_MANIFEST = RunManifest(
    source_id="metoffice-ostia-sst",
    fields=(RequiredField("sea_surface_temperature", "degC"), RequiredField("sea_surface_temperature_uncertainty", "degC"), RequiredField("sea_surface_temperature_mask", "flag")),
    min_coverage_fraction=0.05,
    bounds=EVIDENCE_BOUNDS,
)
OISST_MANIFEST = RunManifest(
    source_id="noaa-oisst-v2-1",
    fields=(RequiredField("sea_surface_temperature", "degC"), RequiredField("sea_surface_temperature_uncertainty", "degC")),
    min_coverage_fraction=0.05,
    bounds=EVIDENCE_BOUNDS,
)


def _aware(value: numpy.datetime64) -> datetime:
    seconds = value.astype("datetime64[s]").astype(int)
    return datetime.fromtimestamp(int(seconds), UTC)


def _download_bytes(client: PoliteClient, url: str, workdir: Path, name: str, ceiling: int) -> bytes:
    path = workdir / name
    client.download(url, path, max_bytes=ceiling)
    return path.read_bytes()


def _decode_chunk(payload: bytes, metadata: Mapping[str, Any]) -> numpy.ndarray:
    if metadata.get("order") != "C" or metadata.get("filters") not in (None, []):
        raise AdapterUnavailable("OSTIA Zarr chunk uses an unsupported order or filter pipeline")
    decoded = get_codec(metadata["compressor"]).decode(payload) if metadata.get("compressor") else payload
    return numpy.frombuffer(decoded, dtype=numpy.dtype(metadata["dtype"]))


def _validate_ostia_metadata(metadata: Mapping[str, Any]) -> None:
    required = ("time", "latitude", "longitude", "analysed_sst", "analysis_error", "mask")
    for name in required:
        if f"{name}/.zarray" not in metadata or f"{name}/.zattrs" not in metadata:
            raise AdapterUnavailable(f"OSTIA consolidated metadata is missing {name}")
        spec = metadata[f"{name}/.zarray"]
        if spec.get("zarr_format") != 2 or spec.get("order") != "C" or spec.get("filters") not in (None, []):
            raise AdapterUnavailable(f"OSTIA {name} has an unsupported Zarr layout")
    for name in ("latitude", "longitude"):
        spec = metadata[f"{name}/.zarray"]
        if len(spec["shape"]) != 1 or list(spec["chunks"]) != list(spec["shape"]):
            raise AdapterUnavailable(f"OSTIA {name} is no longer a single native coordinate chunk")
    for name in ("analysed_sst", "analysis_error", "mask"):
        spec = metadata[f"{name}/.zarray"]
        if len(spec["shape"]) != 3 or int(spec["chunks"][0]) != 1:
            raise AdapterUnavailable(f"OSTIA {name} is no longer time-chunked one analysis per chunk")
    time_attrs = metadata["time/.zattrs"]
    if time_attrs.get("units") != "seconds since 1981-01-01" or time_attrs.get("calendar") != "proleptic_gregorian":
        raise AdapterUnavailable("OSTIA time units/calendar changed; analysis identity will not be guessed")
    if metadata["analysed_sst/.zattrs"].get("units") != "kelvin" or metadata["analysis_error/.zattrs"].get("units") != "kelvin":
        raise AdapterUnavailable("OSTIA native SST/error units changed from kelvin")
    mask_attrs = metadata["mask/.zattrs"]
    if mask_attrs.get("flag_masks") != [1, 2, 4, 8, 16] or mask_attrs.get("flag_meanings") != "water land optional_lake_surface sea_ice optional_river_surface":
        raise AdapterUnavailable("OSTIA native surface-mask declaration changed")


def _crop(ds: xarray.Dataset) -> xarray.Dataset:
    latitude = "latitude" if "latitude" in ds.coords else "lat"
    longitude = "longitude" if "longitude" in ds.coords else "lon"
    lats = numpy.asarray(ds[latitude].values)
    lons = numpy.asarray(ds[longitude].values)
    # OISST uses 0..360; OSTIA uses -180..180.
    west = EVIDENCE_BOUNDS["west"] % 360 if float(lons.max()) > 180 else EVIDENCE_BOUNDS["west"]
    east = EVIDENCE_BOUNDS["east"] % 360 if float(lons.max()) > 180 else EVIDENCE_BOUNDS["east"]
    lat_idx = numpy.nonzero((lats >= EVIDENCE_BOUNDS["south"]) & (lats <= EVIDENCE_BOUNDS["north"]))[0]
    lon_idx = numpy.nonzero((lons >= west) & (lons <= east))[0]
    if not lat_idx.size or not lon_idx.size:
        raise AdapterUnavailable("SST crop selected no cells in the evidence box")
    cropped = ds.isel({latitude: slice(int(lat_idx.min()), int(lat_idx.max()) + 1), longitude: slice(int(lon_idx.min()), int(lon_idx.max()) + 1)})
    if latitude != "latitude" or longitude != "longitude":
        cropped = cropped.rename({latitude: "latitude", longitude: "longitude"})
    if float(cropped.longitude.max()) > 180:
        cropped = cropped.assign_coords(longitude=((cropped.longitude + 180) % 360) - 180).sortby("longitude")
    return cropped


def _provenance(source_id: str, product: str, resolution: str, verdict: Any, manifest: RunManifest, *, revision: str, adapter_version: str, identity: str, urls: list[str], retrieved_at: datetime) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "producer": "Met Office" if source_id == "metoffice-ostia-sst" else "NOAA National Centers for Environmental Information",
        "product": product,
        "product_identity": identity,
        "artifact_revision": revision,
        "adapter_version": adapter_version,
        "native_resolution": resolution,
        "native_crs": "EPSG:4326",
        "retrieval_time": retrieved_at.isoformat(),
        "source_urls": urls,
        "original_units": {
            "sea_surface_temperature": "kelvin" if source_id == "metoffice-ostia-sst" else "Celsius",
            "sea_surface_temperature_uncertainty": "kelvin" if source_id == "metoffice-ostia-sst" else "Celsius",
            **({"sea_surface_temperature_mask": "native bit mask"} if source_id == "metoffice-ostia-sst" else {}),
        },
        "quality": verdict.as_quality(),
        "coverage": verdict.as_coverage(),
        **manifest.as_manifest_block(),
    }


class OSTIAAdapter:
    source_id = "metoffice-ostia-sst"
    adapter_version = "ostia-timechunked-v1"

    def __init__(self, client: PoliteClient | None = None, root: str = OSTIA_ROOT) -> None:
        self._client, self._root = client, root.rstrip("/")

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            meta = json.loads(client.get_bytes(f"{self._root}/.zmetadata", max_bytes=MAX_METADATA_BYTES))
            _validate_ostia_metadata(meta["metadata"])
            array = meta["metadata"]["time/.zarray"]
            chunk_index = (int(array["shape"][0]) - 1) // int(array["chunks"][0])
            payload = client.get_bytes(f"{self._root}/time/{chunk_index}", max_bytes=MAX_METADATA_BYTES)
            values = _decode_chunk(payload, array)
            valid = values[values > 0]
            if not valid.size:
                raise ValueError("latest time chunk carries no valid timestamps")
            moment = datetime(1981, 1, 1, tzinfo=UTC) + timedelta(seconds=int(valid[-1]))
        except Exception as error:
            raise AdapterUnavailable(f"OSTIA metadata discovery failed: {error}") from error
        if not window.covers(moment):
            raise AdapterUnavailable(f"latest OSTIA analysis {moment.isoformat()} is outside the evidence window")
        return [RunCandidate(f"ostia-{moment:%Y%m%d}", moment, [f"{self._root}/.zmetadata"], {"metadata": meta, "time_index": int(array["shape"][0]) - 1})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client, metadata = self._get_client(), candidate.detail["metadata"]["metadata"]
        arrays: dict[str, numpy.ndarray] = {}
        coords: dict[str, numpy.ndarray] = {}
        urls: list[str] = []
        for name in ("latitude", "longitude"):
            spec = metadata[f"{name}/.zarray"]
            url = f"{self._root}/{name}/0"; urls.append(url)
            coords[name] = _decode_chunk(_download_bytes(client, url, workdir, f"ostia-{name}.chunk", MAX_CHUNK_BYTES), spec)[: spec["shape"][0]]
        lat_all, lon_all = coords["latitude"], coords["longitude"]
        lat_idx = numpy.nonzero((lat_all >= EVIDENCE_BOUNDS["south"]) & (lat_all <= EVIDENCE_BOUNDS["north"]))[0]
        lon_idx = numpy.nonzero((lon_all >= EVIDENCE_BOUNDS["west"]) & (lon_all <= EVIDENCE_BOUNDS["east"]))[0]
        if not lat_idx.size or not lon_idx.size:
            raise AdapterUnavailable("OSTIA native grid has no cells in the evidence box")
        time_index = int(candidate.detail["time_index"])
        for upstream in ("analysed_sst", "analysis_error", "mask"):
            spec = metadata[f"{upstream}/.zarray"]
            cy, cx = int(spec["chunks"][1]), int(spec["chunks"][2])
            if cy <= 0 or cx <= 0:
                raise AdapterUnavailable("OSTIA native chunk dimensions must be positive")
            ychunks, xchunks = numpy.unique(lat_idx // cy), numpy.unique(lon_idx // cx)
            if len(ychunks) * len(xchunks) > MAX_OSTIA_CHUNKS_PER_FIELD:
                raise AdapterUnavailable("OSTIA evidence box exceeds its native chunk-count ceiling")
            subset = numpy.empty((lat_idx.size, lon_idx.size), dtype=numpy.dtype(spec["dtype"]))
            for ychunk in ychunks:
                rows = numpy.flatnonzero(lat_idx // cy == ychunk)
                for xchunk in xchunks:
                    columns = numpy.flatnonzero(lon_idx // cx == xchunk)
                    chunk_id = f"{time_index}.{ychunk}.{xchunk}"
                    url = f"{self._root}/{upstream}/{chunk_id}"; urls.append(url)
                    raw = _decode_chunk(_download_bytes(client, url, workdir, f"ostia-{upstream}-{chunk_id}.chunk", MAX_CHUNK_BYTES), spec).reshape((cy, cx))
                    subset[numpy.ix_(rows, columns)] = raw[numpy.ix_(lat_idx[rows] - ychunk * cy, lon_idx[columns] - xchunk * cx)]
            attrs = metadata[f"{upstream}/.zattrs"]
            if upstream != "mask":
                missing = subset == spec.get("fill_value")
                subset = subset.astype("float32") * float(attrs.get("scale_factor", 1)) + float(attrs.get("add_offset", 0))
                subset[missing] = numpy.nan
            arrays[upstream] = subset
        mask = arrays["mask"].astype("int8")
        water = ((mask & 1) != 0) & (mask != metadata["mask/.zarray"].get("fill_value"))
        sst = numpy.where(water, arrays["analysed_sst"] - 273.15, numpy.nan)
        uncertainty = numpy.where(water, arrays["analysis_error"], numpy.nan)
        valid_time = numpy.datetime64(candidate.run_time.replace(tzinfo=None), "ns")
        ds = xarray.Dataset(
            {
                "sea_surface_temperature": (("valid_time", "latitude", "longitude"), sst[None], {"units": "degC", "original_units": "kelvin", "standard_name": "sea_surface_foundation_temperature"}),
                "sea_surface_temperature_uncertainty": (("valid_time", "latitude", "longitude"), uncertainty[None], {"units": "degC", "original_units": "kelvin", "long_name": "OSTIA analysis error standard deviation"}),
                "sea_surface_temperature_mask": (("valid_time", "latitude", "longitude"), mask[None], {"units": "flag", "flag_masks": [1, 2, 4, 8, 16], "flag_meanings": "water land optional_lake_surface sea_ice optional_river_surface"}),
            },
            coords={"valid_time": [valid_time], "latitude": lat_all[lat_idx], "longitude": lon_all[lon_idx]},
        )
        verdict = validate_run(OSTIA_MANIFEST, ds, window=window, upstream_fields=("analysed_sst", "analysis_error", "mask"), retrieved_fields=("analysed_sst", "analysis_error", "mask"))
        retrieved_at = datetime.now(UTC)
        path = workdir / "metoffice-ostia-sst.zarr.zip"; write_zarr(ds, path)
        revision = f"{candidate.provider_run_id}-{hashlib.sha256(path.read_bytes()).hexdigest()[:16]}"
        provenance = _provenance(self.source_id, "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2", "0.05 degree", verdict, OSTIA_MANIFEST, revision=revision, adapter_version=self.adapter_version, identity="near-real-time Level 4 daily foundation SST analysis", urls=urls, retrieved_at=retrieved_at)
        return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time, retrieved_at, verdict.complete, verdict.qc_passed, [Artifact("sst_analysis", MEDIA_ZARR, path, provenance)], "EPSG:4326", "No fog inference; land masked using the native OSTIA bit mask.")


class OISSTAdapter:
    source_id = "noaa-oisst-v2-1"
    adapter_version = "oisst-v2r01-v1"

    def __init__(self, client: PoliteClient | None = None, root: str = OISST_ROOT) -> None:
        self._client, self._root = client, root.rstrip("/")

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        for offset in range(0, 5):
            day = (window.now - timedelta(days=offset)).date()
            directory = f"{self._root}/{day:%Y%m}/"
            try:
                listing = client.get_bytes(directory, max_bytes=MAX_METADATA_BYTES).decode("utf-8")
                names = parse_directory_listing(listing, suffixes=(".nc",))
            except Exception:
                continue
            pattern = re.compile(rf"oisst-avhrr-v02r01\.{day:%Y%m%d}(?:_preliminary)?\.nc$")
            matches = [name for name in names if pattern.fullmatch(name)]
            if matches:
                name = sorted(matches, key=lambda value: "_preliminary" in value)[0]
                moment = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
                if not window.covers(moment):
                    continue
                return [RunCandidate(f"oisst-{day:%Y%m%d}{'-preliminary' if '_preliminary' in name else '-final'}", moment, [directory + name], {"filename": name, "identity": "preliminary" if "_preliminary" in name else "final"})]
        raise AdapterUnavailable("NOAA OISST published no current final or preliminary file in the last five days")

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        url = candidate.urls[0]; raw_path = workdir / candidate.detail["filename"]
        self._get_client().download(url, raw_path, max_bytes=MAX_OISST_BYTES)
        with xarray.open_dataset(raw_path) as upstream:
            required = {"sst", "err"}
            if not required.issubset(upstream.data_vars):
                raise AdapterUnavailable(f"OISST missing required fields: {sorted(required - set(upstream.data_vars))}")
            if upstream["sst"].attrs.get("units") != "Celsius" or upstream["err"].attrs.get("units") != "Celsius":
                raise AdapterUnavailable("OISST native SST/error units changed from Celsius")
            identity = upstream.attrs.get("id")
            if not isinstance(identity, str) or identity != candidate.detail["filename"]:
                raise AdapterUnavailable("OISST file id does not match the discovered final/preliminary product identity")
            if "OISST" not in str(upstream.attrs.get("title", "")):
                raise AdapterUnavailable("OISST title no longer identifies the NOAA OISST analysis")
            ds = _crop(upstream[["sst", "err"]].squeeze("zlev", drop=True).load()).rename({"sst": "sea_surface_temperature", "err": "sea_surface_temperature_uncertainty", "time": "valid_time"})
        actual_time = _aware(numpy.asarray(ds.valid_time.values)[0])
        if actual_time != candidate.run_time or not window.covers(actual_time):
            raise AdapterUnavailable("OISST native analysis time differs from discovery or is outside the evidence window")
        ds["sea_surface_temperature"].attrs.update(units="degC", original_units="Celsius", standard_name="sea_surface_temperature")
        ds["sea_surface_temperature_uncertainty"].attrs.update(units="degC", original_units="Celsius", long_name="estimated error standard deviation of analysed SST")
        verdict = validate_run(OISST_MANIFEST, ds, window=window, upstream_fields=("sst", "anom", "err", "ice"), retrieved_fields=("sst", "err"))
        retrieved_at = datetime.now(UTC); path = workdir / "noaa-oisst-v2-1.zarr.zip"; write_zarr(ds, path)
        revision = f"{candidate.provider_run_id}-{hashlib.sha256(path.read_bytes()).hexdigest()[:16]}"
        provenance = _provenance(self.source_id, "NOAA 0.25-degree Daily OISST AVHRR-only v2.1", "0.25 degree", verdict, OISST_MANIFEST, revision=revision, adapter_version=self.adapter_version, identity=identity, urls=[url], retrieved_at=retrieved_at)
        return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time, retrieved_at, verdict.complete, verdict.qc_passed, [Artifact("sst_analysis", MEDIA_ZARR, path, provenance)], "EPSG:4326", "No fog inference; native missing SST cells remain masked.")
