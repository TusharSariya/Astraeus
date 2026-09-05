"""GOES-19 GLM Lightning Cluster-Filter Algorithm — ISOLATED, EXPERIMENTAL.

``GLM-L2-LCFA`` from the anonymous public ``noaa-goes19`` bucket: one file
every 20 seconds carrying the three levels of the cluster hierarchy — events
(single pixel-integration detections), groups (events clustered in one frame)
and flashes (groups clustered in time and space).

Like ``goes_abi_dmw``, this module is an acquisition probe. It is not
registered, is deliberately absent from ``ingest.adapters.__init__``, and every
artifact it stages declares ``operational: False``.

Two facts about lightning shape this adapter. First, all three levels are
published rather than flashes alone: a flash centroid is the mean of its
groups, so at the scale of an 8 km footprint the groups and events are the
detections and the flash is a summary of them. Each feature says which it is.
Second, nothing is inferred from a file's absence of lightning. Over the
evidence box, most 20-second files hold no in-box detection at all — the
observed 19:37:20 file carried 1,232 flashes worldwide and none in the box —
and that publishes as an empty collection with the counts that prove the files
were read, never as a gap.

The declared field of view is read from the file (``lat_field_of_view_bounds``
and ``lon_field_of_view_bounds``) and checked to contain the requested bounds.
A file whose own metadata says it cannot see the box is refused rather than
published as an empty detection: "no lightning" and "not looking" are
different answers and must not collapse into one.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy
import xarray

from ingest.adapters.goes_abi import (
    GOES_S3_BASE,
    _hour_prefix,
    parse_bucket_keys,
    parse_scan_stamp,
)
from ingest.contract import (
    EVIDENCE_BOX_BOUNDS,
    MEDIA_GEOJSON,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.http import PoliteClient
from ingest.manifest import declared_classes

UTC = timezone.utc
_log = logging.getLogger(__name__)

GLM_PRODUCT = "GLM-L2-LCFA"
LOGICAL_NAME = "glm_lcfa"

#: The interval one operation covers, and the ceiling on how many 20-second
#: files that may become. Ten minutes is 30 files exactly; the cap is stated
#: separately so a provider that ever publishes a denser cadence cannot turn
#: one operation into an unbounded pull.
INTERVAL = timedelta(minutes=10)
MAX_FILES = 30

#: An observed LCFA file is ~0.7 MB in an active hour. The ceiling aborts a
#: runaway body mid-stream, leaving no partial file behind.
MAX_FILE_BYTES = 2 * 1024 * 1024

DQF_RULE = (
    "kept all detections; quality_flag 0 = good_quality_qf, 1/3/5 are the "
    "provider's degraded codes and travel with the feature rather than "
    "removing it"
)
FIELD_NAME_NOTE = (
    "this artifact's served field name is lightning_flash_glm; the GLM file "
    "itself names nothing that way, and the mapping is recorded here so a "
    "reader is never left inferring it from a variable name"
)

REQUIRED_VARIABLES = (
    "flash_lat",
    "flash_lon",
    "flash_energy",
    "flash_area",
    "flash_quality_flag",
    "flash_id",
    "flash_time_offset_of_first_event",
    "flash_time_offset_of_last_event",
    "group_lat",
    "group_lon",
    "group_energy",
    "group_area",
    "group_quality_flag",
    "group_id",
    "group_parent_flash_id",
    "group_time_offset",
    "event_lat",
    "event_lon",
    "event_energy",
    "event_id",
    "event_parent_group_id",
    "event_time_offset",
    "lat_field_of_view_bounds",
    "lon_field_of_view_bounds",
)


class FieldOfViewRefusal(ValueError):
    """The file's own declared field of view does not contain the crop box."""


def parse_glm_key(key: str) -> str | None:
    """The 14-digit scan-start stamp of an LCFA object key, else ``None``."""
    name = key.rsplit("/", 1)[-1]
    if not name.startswith(f"OR_{GLM_PRODUCT}_G19_s") or not name.endswith(".nc"):
        return None
    parts = name[:-3].split("_")
    if len(parts) != 6:
        return None
    stamp = parts[3][1:]
    if len(stamp) != 14 or not stamp.isdigit():
        return None
    return stamp


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    import pandas  # noqa: PLC0415

    stamp = pandas.Timestamp(value)
    if stamp is pandas.NaT or stamp != stamp:  # noqa: PLR0124 - NaT is not equal to itself
        return None
    # ``isoformat`` on the Timestamp itself, never ``to_pydatetime``: GLM
    # offsets carry nanoseconds, and datetime would silently round them away.
    return (stamp if stamp.tz is not None else stamp.tz_localize(UTC)).isoformat()


def _meanings(variable: Any) -> list[str]:
    raw = variable.attrs.get("flag_meanings")
    return str(raw).split() if raw else []


def _meaning_for(flag: Any, values: Sequence[int], meanings: Sequence[str]) -> str | None:
    if flag is None:
        return None
    for candidate, meaning in zip(values, meanings):
        if int(candidate) == int(flag):
            return meaning
    return None


def _number(value: Any) -> float | None:
    result = float(value)
    return None if not numpy.isfinite(result) else result


def field_of_view(dataset: xarray.Dataset) -> dict[str, float]:
    """The file's own declared field of view, ordered south/north, west/east.

    The provider writes latitude bounds north-first (``[57.6, -57.6]``), so the
    pair is sorted here rather than positionally unpacked.
    """
    latitudes = [float(value) for value in numpy.atleast_1d(dataset["lat_field_of_view_bounds"].values)]
    longitudes = [float(value) for value in numpy.atleast_1d(dataset["lon_field_of_view_bounds"].values)]
    if len(latitudes) < 2 or len(longitudes) < 2:
        raise FieldOfViewRefusal("GLM file declares an incomplete field of view")
    return {
        "south": min(latitudes),
        "north": max(latitudes),
        "west": min(longitudes),
        "east": max(longitudes),
    }


def assert_field_of_view_contains(view: Mapping[str, float], bounds: Mapping[str, float]) -> None:
    if not (
        view["south"] <= float(bounds["south"])
        and view["north"] >= float(bounds["north"])
        and view["west"] <= float(bounds["west"])
        and view["east"] >= float(bounds["east"])
    ):
        raise FieldOfViewRefusal(
            f"GLM declared field of view {dict(view)} does not contain {dict(bounds)}; "
            "an unobserved box is not an empty detection"
        )


def read_detections(
    path: Path, *, bounds: Mapping[str, float]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Decode one LCFA file into in-box features plus its own counts.

    xarray's default decoding honours ``_Unsigned`` on the packed int16
    coordinates and energies, so the values here are the provider's physical
    units rather than raw counts. Decoded coordinates are range-checked before
    anything is published: a coordinate outside [-90, 90] / [-180, 180] means
    the packing was misread, which must fail loudly rather than plot.
    """
    with xarray.open_dataset(path, engine="netcdf4") as dataset:
        missing = [name for name in REQUIRED_VARIABLES if name not in dataset.variables]
        if missing:
            raise ValueError(f"GLM file does not carry {missing}")
        start_text = dataset.attrs.get("time_coverage_start")
        if not start_text:
            raise ValueError("GLM file carries no time_coverage_start; the key stamp is not scan time")
        scan_start = datetime.fromisoformat(str(start_text).replace("Z", "+00:00")).astimezone(UTC)
        end_text = dataset.attrs.get("time_coverage_end")
        scan_end = (
            datetime.fromisoformat(str(end_text).replace("Z", "+00:00")).astimezone(UTC)
            if end_text
            else None
        )
        view = field_of_view(dataset)
        assert_field_of_view_contains(view, bounds)

        source_file = str(dataset.attrs.get("dataset_name") or path.name)
        platform = str(dataset.attrs.get("platform_ID", ""))
        spatial_resolution = str(dataset.attrs.get("spatial_resolution", ""))

        levels: dict[str, dict[str, Any]] = {}
        for kind, prefix in (("flash", "flash"), ("group", "group"), ("event", "event")):
            entry: dict[str, Any] = {
                "lat": numpy.asarray(dataset[f"{prefix}_lat"].values, dtype="float64"),
                "lon": numpy.asarray(dataset[f"{prefix}_lon"].values, dtype="float64"),
                "energy": numpy.asarray(dataset[f"{prefix}_energy"].values, dtype="float64"),
                "id": numpy.asarray(dataset[f"{prefix}_id"].values),
            }
            if kind == "event":
                entry["area"] = None
                entry["quality"] = None
                entry["quality_values"] = []
                entry["quality_meanings"] = []
                entry["parent"] = numpy.asarray(dataset["event_parent_group_id"].values)
                entry["time"] = dataset["event_time_offset"].values
            else:
                flag_variable = dataset[f"{prefix}_quality_flag"]
                entry["area"] = numpy.asarray(dataset[f"{prefix}_area"].values, dtype="float64")
                entry["quality"] = numpy.asarray(flag_variable.values, dtype="float64")
                entry["quality_values"] = [
                    int(value) for value in numpy.atleast_1d(flag_variable.attrs.get("flag_values", []))
                ]
                entry["quality_meanings"] = _meanings(flag_variable)
                if kind == "group":
                    entry["parent"] = numpy.asarray(dataset["group_parent_flash_id"].values)
                    entry["time"] = dataset["group_time_offset"].values
                else:
                    entry["parent"] = None
                    entry["time_first"] = dataset["flash_time_offset_of_first_event"].values
                    entry["time_last"] = dataset["flash_time_offset_of_last_event"].values
            levels[kind] = entry

    features: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    coordinates_in_range = True
    for kind in ("flash", "group", "event"):
        entry = levels[kind]
        latitude = entry["lat"]
        longitude = entry["lon"]
        finite = numpy.isfinite(latitude) & numpy.isfinite(longitude)
        if not bool(
            numpy.all(numpy.abs(latitude[finite]) <= 90.0)
            and numpy.all(numpy.abs(longitude[finite]) <= 180.0)
        ):
            coordinates_in_range = False
        inside = (
            finite
            & (latitude >= float(bounds["south"]))
            & (latitude <= float(bounds["north"]))
            & (longitude >= float(bounds["west"]))
            & (longitude <= float(bounds["east"]))
        )
        indices = numpy.nonzero(inside)[0]
        counts[f"{kind}es" if kind == "flash" else f"{kind}s"] = int(latitude.size)
        counts[f"in_box_{kind}es" if kind == "flash" else f"in_box_{kind}s"] = int(indices.size)
        if entry["quality"] is not None:
            counts[f"in_box_good_{kind}es" if kind == "flash" else f"in_box_good_{kind}s"] = int(
                numpy.count_nonzero(inside & (entry["quality"] == 0.0))
            )
        for index in indices:
            flag = (
                int(entry["quality"][index])
                if entry["quality"] is not None and numpy.isfinite(entry["quality"][index])
                else None
            )
            properties: dict[str, Any] = {
                "kind": kind,
                "id": int(entry["id"][index]),
                "parent_id": None if entry["parent"] is None else int(entry["parent"][index]),
                "energy_j": _number(entry["energy"][index]),
                "area_m2": None if entry["area"] is None else _number(entry["area"][index]),
                "quality_flag": flag,
                "quality_meaning": _meaning_for(flag, entry["quality_values"], entry["quality_meanings"]),
                "source_file": source_file,
            }
            if kind == "flash":
                properties["time_first"] = _iso(entry["time_first"][index])
                properties["time_last"] = _iso(entry["time_last"][index])
            else:
                properties["time"] = _iso(entry["time"][index])
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [round(float(longitude[index]), 6), round(float(latitude[index]), 6)],
                    },
                    "properties": properties,
                }
            )

    stats = {
        "scan_start": scan_start,
        "scan_end": scan_end,
        "platform_ID": platform,
        "spatial_resolution": spatial_resolution,
        "source_file": source_file,
        "field_of_view": view,
        "counts": counts,
        "coordinates_in_range": coordinates_in_range,
    }
    return features, stats


class GOESLightningAdapter:
    """Acquisition probe for GLM-L2-LCFA. Never registered, never operational.

    ``source_id`` names the registry record another change is adding. Nothing
    here reads the registry, so the probe runs whether or not that record
    exists yet; the id is a label on the provenance, not a lookup.
    """

    source_id = "noaa-goes-glm"
    adapter_version = "goes-glm-lcfa-v1"
    logical_name = LOGICAL_NAME

    def __init__(
        self,
        *,
        base_url: str = GOES_S3_BASE,
        bounds: Mapping[str, float] = EVIDENCE_BOX_BOUNDS,
        interval: timedelta = INTERVAL,
        max_files: int = MAX_FILES,
        client: PoliteClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bounds = dict(bounds)
        self._interval = interval
        self._max_files = max_files
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        interval_end = window.now
        interval_start = interval_end - self._interval
        prefixes: list[str] = []
        for moment in (interval_start, interval_end):
            prefix = _hour_prefix(GLM_PRODUCT, moment)
            if prefix not in prefixes:
                prefixes.append(prefix)

        selected: dict[str, str] = {}
        listed_any = False
        for prefix in prefixes:
            url = f"{self._base_url}/?list-type=2&prefix={prefix}"
            try:
                text = client.get_text(url)
            except Exception as error:  # noqa: BLE001 - one missing hour is not an outage
                _log.warning("GOES GLM listing failed for %s: %s", url, error)
                continue
            listed_any = True
            for key in parse_bucket_keys(text):
                stamp = parse_glm_key(key)
                if stamp is None:
                    continue
                scan_start = parse_scan_stamp(stamp)
                if interval_start <= scan_start <= interval_end:
                    selected[stamp] = key
        if not selected:
            raise AdapterUnavailable(
                "no GOES-19 GLM-L2-LCFA files listed for "
                f"{interval_start.isoformat()}..{interval_end.isoformat()}"
                + ("" if listed_any else " (no hour prefix could be listed)")
            )
        stamps = sorted(selected)[: self._max_files]
        keys = {stamp: selected[stamp] for stamp in stamps}
        return [
            RunCandidate(
                provider_run_id=f"goes19-glm-lcfa-{stamps[0]}-{stamps[-1]}",
                run_time=interval_start,
                urls=[f"{self._base_url}/{key}" for key in keys.values()],
                detail={
                    "product": GLM_PRODUCT,
                    "keys": keys,
                    "interval_start": interval_start.isoformat(),
                    "interval_end": interval_end.isoformat(),
                    "prefixes": prefixes,
                    "listed_files": len(selected),
                    "capped_at": self._max_files,
                },
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        retrieved_at = datetime.now(UTC)
        keys: dict[str, str] = dict(candidate.detail.get("keys") or {})
        if not keys:
            raise AdapterUnavailable("GLM candidate lists no files")

        features: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        valid_times: list[str] = []
        totals: dict[str, int] = {}
        view: dict[str, float] = {}
        platform = ""
        spatial_resolution = ""
        coordinates_in_range = True

        for stamp in sorted(keys):
            key = keys[stamp]
            url = f"{self._base_url}/{key}"
            path = workdir / Path(key).name
            written = client.download(url, path, max_bytes=MAX_FILE_BYTES)
            file_features, stats = read_detections(path, bounds=self._bounds)
            features.extend(file_features)
            files.append(
                {
                    "key": key,
                    "url": url,
                    "bytes": int(written),
                    "sha256": _sha256(path),
                    "scan_start": stats["scan_start"].isoformat(),
                }
            )
            valid_times.append(stats["scan_start"].isoformat())
            for name, value in stats["counts"].items():
                totals[name] = totals.get(name, 0) + int(value)
            coordinates_in_range = coordinates_in_range and bool(stats["coordinates_in_range"])
            view = view or stats["field_of_view"]
            platform = platform or stats["platform_ID"]
            spatial_resolution = spatial_resolution or stats["spatial_resolution"]

        stamps = sorted(keys)
        geojson_path = workdir / f"{LOGICAL_NAME}_{stamps[0]}_{stamps[-1]}.geojson"
        geojson_path.parent.mkdir(parents=True, exist_ok=True)
        geojson_path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                    "features": features,
                },
                ensure_ascii=False,
            ),
            "utf-8",
        )

        interval_start = datetime.fromisoformat(str(candidate.detail["interval_start"]))
        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA / NESDIS",
            "product": "GOES-19 GLM L2 Lightning Detections (Cluster-Filter Algorithm)",
            "product_id": GLM_PRODUCT,
            "prefixes": candidate.detail.get("prefixes"),
            "files": files,
            "interval_start": candidate.detail.get("interval_start"),
            "interval_end": candidate.detail.get("interval_end"),
            "valid_times": sorted(set(valid_times)),
            "platform_ID": platform,
            "spatial_resolution": spatial_resolution,
            "counts": {"files": len(files), **totals},
            "field_of_view_bounds": view,
            "bounds": dict(self._bounds),
            "field_name_note": FIELD_NAME_NOTE,
            "dqf_rule": DQF_RULE,
            "empty_is_an_answer": (
                "an interval with no in-box detection publishes as features: [] with the "
                "per-level counts that prove every file was read; that is an empty "
                "detection, not a failed retrieval"
            ),
            "operational": False,
            "adapter_version": self.adapter_version,
            **declared_classes(["retrieved"]),
        }

        artifact = Artifact(
            logical_name=LOGICAL_NAME,
            media_type=MEDIA_GEOJSON,
            payload_path=geojson_path,
            provenance=provenance,
        )
        complete = len(files) == len(keys)
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=interval_start,
            retrieved_at=retrieved_at,
            complete=complete,
            qc_passed=coordinates_in_range,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=(
                f"{len(files)} LCFA file(s) over {candidate.detail.get('interval_start')}"
                f"..{candidate.detail.get('interval_end')}; "
                f"{len(features)} detection(s) in the evidence box"
            ),
        )


__all__: Sequence[str] = (
    "DQF_RULE",
    "FIELD_NAME_NOTE",
    "GLM_PRODUCT",
    "INTERVAL",
    "LOGICAL_NAME",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "FieldOfViewRefusal",
    "GOESLightningAdapter",
    "assert_field_of_view_contains",
    "field_of_view",
    "parse_glm_key",
    "read_detections",
)
