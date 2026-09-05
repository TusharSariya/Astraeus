"""GOES-19 ABI Derived Motion Winds — ISOLATED, EXPERIMENTAL acquisition.

Two products from the anonymous public ``noaa-goes19`` bucket:

``ABI-L2-DMWF``
    Cloud-tracked atmospheric motion vectors, one Full Disk file per ABI band
    per scan (C02, C07, C08, C09, C10, C14 are the bands NESDIS publishes).
``ABI-L2-DMWVF``
    Clear-sky water-vapour motion vectors, bands C08 and C10.

Nothing here reaches the registry. The module is deliberately absent from
``ingest.adapters.__init__``, calls no ``ingest.registry.register``, and every
artifact it stages declares ``operational: False``. It is an acquisition probe:
it proves the bytes can be pulled, decoded and read back through the API, and
it says so about itself so nothing downstream can mistake it for a source this
deployment stands behind.

What is published is what was retrieved. A vector is carried through with the
provider's own numbers — speed, from-direction, pressure, tracer brightness
temperature, both zenith angles, its DQF and that flag's meaning — and nothing
is computed, smoothed, thinned or gap-filled. Every DQF value is kept rather
than filtered to ``good_wind_qf``: the flag travels with the vector so a reader
decides, and the provenance counts good and total separately.

An empty crop is an answer, not a failure. DMWVF over the evidence box is
routinely empty (clear-sky water-vapour tracers are sparse at these latitudes),
and that publishes as ``features: []`` with ``in_box_vectors: 0`` in the
provenance, which is distinguishable from a retrieval that never happened.
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

DMWF_PRODUCT = "ABI-L2-DMWF"
DMWVF_PRODUCT = "ABI-L2-DMWVF"

#: Bands NESDIS publishes a Full Disk DMW file for. Discovery does not assume
#: the set is complete for a given scan: whatever is listed is fetched, and the
#: bands that were absent are named in the provenance.
DMWF_BANDS: tuple[str, ...] = ("C02", "C07", "C08", "C09", "C10", "C14")
DMWVF_BANDS: tuple[str, ...] = ("C08", "C10")

#: Observed sizes on 2026-09-05: a DMWF C14 file is ~1.09 MB, a DMWVF C08 file
#: ~0.23 MB. The ceilings leave headroom for a busier scene and abort a
#: runaway body mid-stream.
MAX_DMWF_BYTES = 4 * 1024 * 1024
MAX_DMWVF_BYTES = 2 * 1024 * 1024

#: How far back discovery lists. A granule lands a minute or two after scan
#: end, so the newest hour prefix being empty is normal.
DISCOVERY_HOURS = 4

DQF_RULE = "kept all vectors; dqf 0 = good_wind_qf"

PROPERTY_UNITS = {
    "satellite_motion_wind_speed": "m s-1",
    "satellite_motion_wind_direction": "degree (wind FROM direction, clockwise from north)",
    "pressure_hpa": "hPa",
    "tracer_temperature_k": "K",
    "dqf": "1 (enumerated data quality flag)",
    "local_zenith_angle": "degree",
    "solar_zenith_angle": "degree",
    "observation_time": "ISO 8601 UTC",
}

#: Variables a usable DMW file must carry. A file missing any of them is
#: refused rather than published with the missing quantity silently absent.
REQUIRED_VARIABLES = (
    "lat",
    "lon",
    "wind_speed",
    "wind_direction",
    "pressure",
    "temperature",
    "DQF",
    "local_zenith_angle",
    "solar_zenith_angle",
    "time",
)

_KEY_PREFIX = "OR_"


def parse_dmw_key(key: str) -> tuple[str, str, str] | None:
    """``(product, band, scan_stamp)`` for a DMW object key, else ``None``.

    Written against the key grammar rather than a single regular expression so
    the two products, whose names share a prefix, cannot be confused: DMWVF
    keys start with the DMWF product string.
    """
    name = key.rsplit("/", 1)[-1]
    if not name.startswith(_KEY_PREFIX) or not name.endswith(".nc"):
        return None
    parts = name[:-3].split("_")
    if len(parts) != 6:
        return None
    _prefix, product_mode, platform, start, _end, _created = parts
    if platform != "G19" or not start.startswith("s"):
        return None
    stamp = start[1:]
    if len(stamp) != 14 or not stamp.isdigit():
        return None
    # ``ABI-L2-DMWF-M6C14`` / ``ABI-L2-DMWVF-M6C08``
    head, _, mode_band = product_mode.rpartition("-")
    if not head or len(mode_band) < 4 or mode_band[0] != "M":
        return None
    band = mode_band[2:]
    if len(band) != 3 or band[0] != "C" or not band[1:].isdigit():
        return None
    if head not in (DMWF_PRODUCT, DMWVF_PRODUCT):
        return None
    return head, band, stamp


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dqf_meanings(variable: Any) -> list[str]:
    raw = variable.attrs.get("flag_meanings")
    return str(raw).split() if raw else []


def _dqf_values(variable: Any) -> list[int]:
    return [int(value) for value in numpy.atleast_1d(variable.attrs.get("flag_values", []))]


def _iso(value: Any) -> str:
    """A numpy datetime64 or datetime as an ISO UTC string."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat()
    import pandas  # noqa: PLC0415

    stamp = pandas.Timestamp(value)
    # ``isoformat`` on the Timestamp, never ``to_pydatetime``: the J2000 scan
    # time carries nanoseconds that datetime would silently round away.
    return (stamp if stamp.tz is not None else stamp.tz_localize(UTC)).isoformat()


def _scan_times(dataset: xarray.Dataset) -> tuple[datetime, datetime | None]:
    start_text = dataset.attrs.get("time_coverage_start")
    if not start_text:
        raise ValueError("DMW file carries no time_coverage_start; the key stamp is not scan time")
    start = datetime.fromisoformat(str(start_text).replace("Z", "+00:00")).astimezone(UTC)
    end_text = dataset.attrs.get("time_coverage_end")
    end = (
        datetime.fromisoformat(str(end_text).replace("Z", "+00:00")).astimezone(UTC)
        if end_text
        else None
    )
    return start, end


def read_band_vectors(
    path: Path, band: str, *, bounds: Mapping[str, float]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Decode one DMW file into in-box GeoJSON features plus its own counts.

    xarray's default ``mask_and_scale`` is used, so the provider's fill values
    become NaN rather than being carried as -999 sentinels into the artifact.
    Only vectors with a finite latitude and longitude inside ``bounds`` are
    kept; every DQF value among them is kept, flagged rather than dropped.
    """
    with xarray.open_dataset(path, engine="netcdf4") as dataset:
        missing = [name for name in REQUIRED_VARIABLES if name not in dataset.variables]
        if missing:
            raise ValueError(f"DMW file does not carry {missing}")
        scan_start, scan_end = _scan_times(dataset)

        latitude = numpy.asarray(dataset["lat"].values, dtype="float64")
        longitude = numpy.asarray(dataset["lon"].values, dtype="float64")
        speed = numpy.asarray(dataset["wind_speed"].values, dtype="float64")
        direction = numpy.asarray(dataset["wind_direction"].values, dtype="float64")
        pressure = numpy.asarray(dataset["pressure"].values, dtype="float64")
        temperature = numpy.asarray(dataset["temperature"].values, dtype="float64")
        dqf = numpy.asarray(dataset["DQF"].values, dtype="float64")
        local_zenith = numpy.asarray(dataset["local_zenith_angle"].values, dtype="float64")
        solar_zenith = numpy.asarray(dataset["solar_zenith_angle"].values, dtype="float64")
        observation = dataset["time"].values
        meanings = _dqf_meanings(dataset["DQF"])
        meaning_by_value = dict(zip(_dqf_values(dataset["DQF"]), meanings))
        speed_range = [float(value) for value in numpy.asarray(dataset["wind_speed"].attrs.get("valid_range", [3.0, 155.0]))]
        direction_range = [float(value) for value in numpy.asarray(dataset["wind_direction"].attrs.get("valid_range", [0.0, 360.0]))]
        platform = str(dataset.attrs.get("platform_ID", ""))
        title = str(dataset.attrs.get("title", ""))
        dataset_name = str(dataset.attrs.get("dataset_name", ""))
        production_source = dataset.attrs.get("production_data_source")
        timeline = dataset.attrs.get("timeline_id")
        identifier = dataset.attrs.get("id")
        band_ids = (
            [int(value) for value in numpy.atleast_1d(dataset["band_id"].values)]
            if "band_id" in dataset.variables
            else []
        )

    total = int(latitude.size)
    finite = numpy.isfinite(latitude) & numpy.isfinite(longitude)
    inside = (
        finite
        & (latitude >= float(bounds["south"]))
        & (latitude <= float(bounds["north"]))
        & (longitude >= float(bounds["west"]))
        & (longitude <= float(bounds["east"]))
    )
    indices = numpy.nonzero(inside)[0]

    features: list[dict[str, Any]] = []
    qc_ok = True
    for index in indices:
        flag = dqf[index]
        flag_value = int(flag) if numpy.isfinite(flag) else None
        meaning = meaning_by_value.get(flag_value)
        speed_value = float(speed[index])
        direction_value = float(direction[index])
        if not (
            numpy.isfinite(speed_value)
            and numpy.isfinite(direction_value)
            and speed_range[0] <= speed_value <= speed_range[1]
            and direction_range[0] <= direction_value <= direction_range[1]
        ):
            qc_ok = False
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(longitude[index]), 6), round(float(latitude[index]), 6)],
                },
                "properties": {
                    "band": band,
                    "satellite_motion_wind_speed": _number(speed[index]),
                    "satellite_motion_wind_direction": _number(direction[index]),
                    "pressure_hpa": _number(pressure[index]),
                    "tracer_temperature_k": _number(temperature[index]),
                    "dqf": flag_value,
                    "dqf_meaning": meaning,
                    "local_zenith_angle": _number(local_zenith[index]),
                    "solar_zenith_angle": _number(solar_zenith[index]),
                    "observation_time": _iso(observation[index]),
                },
            }
        )

    stats = {
        "band": band,
        "total_vectors": total,
        "in_box_vectors": int(indices.size),
        "in_box_good_vectors": int(numpy.count_nonzero(inside & (dqf == 0.0))),
        "scan_start": scan_start,
        "scan_end": scan_end,
        "platform_ID": platform,
        "title": title,
        "dataset_name": dataset_name,
        "production_data_source": production_source,
        "timeline_id": timeline,
        "id": identifier,
        "band_ids": band_ids,
        "dqf_flag_meanings": meanings,
        "qc_passed": qc_ok,
        "wind_speed_valid_range": speed_range,
        "wind_direction_valid_range": direction_range,
    }
    return features, stats


def _number(value: Any) -> float | None:
    result = float(value)
    return None if not numpy.isfinite(result) else round(result, 6)


class GOESDerivedMotionWindsAdapter:
    """Acquisition probe for one DMW product. Never registered, never operational."""

    source_id = "noaa-goes-east"
    adapter_version = "goes-abi-dmw-v1"

    def __init__(
        self,
        product: str = DMWF_PRODUCT,
        *,
        base_url: str = GOES_S3_BASE,
        bounds: Mapping[str, float] = EVIDENCE_BOX_BOUNDS,
        client: PoliteClient | None = None,
    ) -> None:
        if product not in (DMWF_PRODUCT, DMWVF_PRODUCT):
            raise ValueError(f"unknown DMW product {product!r}")
        self.product = product
        self.expected_bands = DMWF_BANDS if product == DMWF_PRODUCT else DMWVF_BANDS
        self.max_bytes = MAX_DMWF_BYTES if product == DMWF_PRODUCT else MAX_DMWVF_BYTES
        self.logical_name = "abi_dmwf" if product == DMWF_PRODUCT else "abi_dmwvf"
        self._base_url = base_url.rstrip("/")
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        by_stamp: dict[str, dict[str, str]] = {}
        for hours_back in range(DISCOVERY_HOURS):
            moment = window.now - timedelta(hours=hours_back)
            prefix = _hour_prefix(self.product, moment)
            url = f"{self._base_url}/?list-type=2&max-keys=1000&prefix={prefix}"
            try:
                text = client.get_text(url)
            except Exception as error:  # noqa: BLE001 - one missing hour is not an outage
                _log.warning("GOES DMW listing failed for %s: %s", url, error)
                continue
            for key in parse_bucket_keys(text):
                parsed = parse_dmw_key(key)
                if parsed is None or parsed[0] != self.product:
                    continue
                _product, band, stamp = parsed
                by_stamp.setdefault(stamp, {})[band] = key
        usable = [stamp for stamp in by_stamp if parse_scan_stamp(stamp) <= window.now]
        if not usable:
            raise AdapterUnavailable(
                f"no GOES-19 {self.product} granules listed in the last {DISCOVERY_HOURS} hours"
            )
        stamp = max(usable)
        bands = dict(sorted(by_stamp[stamp].items()))
        scan_start = parse_scan_stamp(stamp)
        return [
            RunCandidate(
                provider_run_id=f"goes19-{self.logical_name.removeprefix('abi_')}-{stamp}",
                run_time=scan_start,
                urls=[f"{self._base_url}/{key}" for key in bands.values()],
                detail={
                    "product": self.product,
                    "scan_stamp": stamp,
                    "band_keys": bands,
                    "prefix": _hour_prefix(self.product, scan_start),
                },
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        retrieved_at = datetime.now(UTC)
        bands: dict[str, str] = dict(candidate.detail.get("band_keys") or {})
        if not bands:
            raise AdapterUnavailable(f"{self.product} candidate lists no band files")

        features: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        per_band: list[dict[str, Any]] = []
        scan_start: datetime | None = None
        scan_end: datetime | None = None
        platform = ""
        title = ""
        meanings: list[str] = []
        qc_passed = True
        fetched: list[str] = []

        for band, key in sorted(bands.items()):
            url = f"{self._base_url}/{key}"
            path = workdir / Path(key).name
            written = client.download(url, path, max_bytes=self.max_bytes)
            band_features, stats = read_band_vectors(path, band, bounds=self._bounds)
            fetched.append(band)
            features.extend(band_features)
            files.append(
                {
                    "band": band,
                    "key": key,
                    "url": url,
                    "bytes": int(written),
                    "sha256": _sha256(path),
                }
            )
            per_band.append(
                {
                    "band": band,
                    "total_vectors": stats["total_vectors"],
                    "in_box_vectors": stats["in_box_vectors"],
                    "in_box_good_vectors": stats["in_box_good_vectors"],
                    "band_id": stats["band_ids"],
                    "dataset_name": stats["dataset_name"],
                    "id": stats["id"],
                }
            )
            qc_passed = qc_passed and bool(stats["qc_passed"])
            qc_passed = qc_passed and stats["in_box_good_vectors"] == stats["in_box_vectors"]
            if stats["platform_ID"] != "G19" or not str(stats["dataset_name"]).startswith(f"OR_{self.product}-M6{band}_G19_"):
                raise ValueError(f"downloaded granule identity does not match {self.product} {band} on G19")
            if scan_start is None:
                scan_start = stats["scan_start"]
                scan_end = stats["scan_end"]
                platform = stats["platform_ID"]
                title = stats["title"]
                meanings = stats["dqf_flag_meanings"]
            elif stats["scan_start"] != scan_start or stats["scan_end"] != scan_end:
                raise ValueError("DMW band granules do not share one scan interval")
            if abs((stats["scan_start"] - parse_scan_stamp(str(candidate.detail.get("scan_stamp", "")))).total_seconds()) > 1.0:
                raise ValueError(f"DMW {band} scan time does not match the discovered object key")

        assert scan_start is not None  # a band was fetched, so a scan time was read
        expected_stamp = str(candidate.detail.get("scan_stamp", ""))
        if expected_stamp and abs((scan_start - parse_scan_stamp(expected_stamp)).total_seconds()) > 1.0:
            raise ValueError("DMW granule scan time does not match the discovered object key")
        geojson_path = workdir / f"{self.logical_name}_{candidate.detail.get('scan_stamp', '')}.geojson"
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

        absent = [band for band in self.expected_bands if band not in bands]
        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA / NESDIS",
            "product": title or f"GOES-19 {self.product}",
            "product_id": self.product,
            "prefix": candidate.detail.get("prefix"),
            "bands_retrieved": fetched,
            "bands_absent": absent,
            "files": files,
            "scan_start": scan_start.isoformat(),
            "scan_end": scan_end.isoformat() if scan_end else None,
            "valid_times": [scan_start.isoformat()],
            "provider_run_id": candidate.provider_run_id,
            "platform_ID": platform,
            "per_band": per_band,
            "total_vectors": sum(entry["total_vectors"] for entry in per_band),
            "in_box_vectors": sum(entry["in_box_vectors"] for entry in per_band),
            "in_box_good_vectors": sum(entry["in_box_good_vectors"] for entry in per_band),
            "bounds": dict(self._bounds),
            "units": dict(PROPERTY_UNITS),
            "dqf_rule": DQF_RULE,
            "dqf_flag_meanings": meanings,
            "empty_is_an_answer": (
                "an in-box collection with no vectors publishes as features: [] with "
                "in_box_vectors 0; that is an empty detection, not a failed retrieval"
            ),
            "operational": False,
            "adapter_version": self.adapter_version,
            **declared_classes(["retrieved"]),
        }

        artifact_digest = _sha256(geojson_path)
        provenance["artifact_revision"] = artifact_digest
        provenance["artifact_sha256"] = artifact_digest

        artifact = Artifact(
            logical_name=self.logical_name,
            media_type=MEDIA_GEOJSON,
            payload_path=geojson_path,
            provenance=provenance,
        )
        complete = sorted(fetched) == sorted(self.expected_bands)
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=scan_start,
            retrieved_at=retrieved_at,
            complete=complete,
            qc_passed=qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=(
                f"{self.product} scan {candidate.detail.get('scan_stamp', '')}: "
                f"{len(fetched)} band(s) fetched, {len(features)} vector(s) in the evidence box"
            ),
        )


def dmwf_adapter(**kwargs: Any) -> GOESDerivedMotionWindsAdapter:
    return GOESDerivedMotionWindsAdapter(DMWF_PRODUCT, **kwargs)


def dmwvf_adapter(**kwargs: Any) -> GOESDerivedMotionWindsAdapter:
    return GOESDerivedMotionWindsAdapter(DMWVF_PRODUCT, **kwargs)


__all__: Sequence[str] = (
    "DMWF_BANDS",
    "DMWF_PRODUCT",
    "DMWVF_BANDS",
    "DMWVF_PRODUCT",
    "DQF_RULE",
    "MAX_DMWF_BYTES",
    "MAX_DMWVF_BYTES",
    "GOESDerivedMotionWindsAdapter",
    "dmwf_adapter",
    "dmwvf_adapter",
    "parse_dmw_key",
    "read_band_vectors",
)
