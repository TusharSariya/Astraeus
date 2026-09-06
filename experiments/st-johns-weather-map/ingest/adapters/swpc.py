"""NOAA SWPC space-weather adapters: planetary Kp, real-time solar wind, OVATION.

Three adapters over the keyless SWPC JSON services, in the AWC pattern:
injectable PoliteClient and URLs, JSON parsed in ``discover`` and carried
through ``RunCandidate.detail``, xarray to zipped Zarr.

Honesty rules specific to space weather:

- Observed and forecast Kp are separate artifacts; the forecast keeps the
  provider's own per-value ``observed|estimated|predicted`` status as a
  flag-coded variable. No lead hours are synthesized.
- The Kp and solar-wind series carry deliberately NO latitude/longitude:
  a planetary quantity must never reach ``/point`` wearing a sample
  distance. Only the OVATION grid - genuinely gridded - keeps coordinates.
- Every timestamp comes from the feed itself; an OVATION payload without its
  own Observation/Forecast Time is refused, never wall-clock stamped.
- The solar-wind source is described as the SWPC real-time solar wind feed;
  no spacecraft is named here because the feed's own ``source`` field is the
  only authority on which spacecraft measured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    MEDIA_ZARR,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import PoliteClient
from ingest.manifest import declared_classes
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

SWPC_BASE = "https://services.swpc.noaa.gov"
KP_OBSERVED_URL = f"{SWPC_BASE}/products/noaa-planetary-k-index.json"
KP_FORECAST_URL = f"{SWPC_BASE}/products/noaa-planetary-k-index-forecast.json"
RTSW_MAG_URL = f"{SWPC_BASE}/json/rtsw/rtsw_mag_1m.json"
OVATION_URL = f"{SWPC_BASE}/json/ovation_aurora_latest.json"

KP_STATUS_VALUES = [0, 1, 2]
KP_STATUS_MEANINGS = "observed estimated predicted"
_KP_STATUS_CODE = {"observed": 0, "estimated": 1, "predicted": 2}


def _parse_time(value: Any) -> datetime | None:
    """A feed ``time_tag`` (or OVATION time) as an aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _records(payload: Any, *, required: tuple[str, ...]) -> list[dict[str, Any]]:
    """SWPC list payloads as dicts.

    The products endpoints have served both a list of objects and a list of
    rows with a header row; both are accepted, anything else is refused by
    the caller receiving an empty list.
    """
    if not isinstance(payload, list) or not payload:
        return []
    if isinstance(payload[0], dict):
        return [record for record in payload if isinstance(record, dict) and all(key in record for key in required)]
    if isinstance(payload[0], list):
        header = [str(name) for name in payload[0]]
        if not all(name in header for name in required):
            return []
        return [dict(zip(header, row)) for row in payload[1:] if isinstance(row, list) and len(row) == len(header)]
    return []


def _float_or_nan(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result


def _series_dataset(times: list[datetime], variables: Mapping[str, tuple[numpy.ndarray, dict[str, Any]]], attrs: Mapping[str, Any]) -> xarray.Dataset:
    """A time-only dataset: deliberately no latitude/longitude coordinates."""
    stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times])
    data_vars = {name: (("valid_time",), values, dict(var_attrs)) for name, (values, var_attrs) in variables.items()}
    return xarray.Dataset(data_vars, coords={"valid_time": stamps}, attrs=dict(attrs))


def _series_quality(name: str, values: numpy.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    """Manual quality/coverage blocks for a coordinate-free series.

    ``validate_run`` requires a horizontal grid by design; these series have
    none on purpose, so their completeness is stated directly: the fraction
    of records carrying a finite value.
    """
    finite = float(numpy.isfinite(values).mean()) if values.size else 0.0
    quality = {
        "status": "passed" if finite > 0.0 else "failed",
        "flags": [] if finite > 0.0 else [f"empty_field:{name}"],
        "detail": f"{name}: {finite:.4f} of records carry a finite value; planetary series, no spatial coverage claimed",
    }
    coverage = {"status": "complete" if finite > 0.0 else "outside", "fraction": round(finite, 4)}
    return quality, coverage


class SWPCKpAdapter:
    """Planetary K index: the observed series and the provider's forecast."""

    source_id = "noaa-swpc-kp"
    adapter_version = "swpc-kp-v1"

    def __init__(self, client: PoliteClient | None = None, observed_url: str = KP_OBSERVED_URL, forecast_url: str = KP_FORECAST_URL) -> None:
        self._client = client
        self._observed_url = observed_url
        self._forecast_url = forecast_url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            observed = _records(client.get(self._observed_url).json(), required=("time_tag", "Kp"))
        except Exception as error:
            raise AdapterUnavailable(f"SWPC Kp endpoint unavailable: {error}") from error
        if not observed:
            raise AdapterUnavailable("SWPC Kp returned no observed records")

        # The forecast feed failing must not stop the observed series.
        forecast: list[dict[str, Any]] = []
        forecast_error = ""
        try:
            forecast = _records(client.get(self._forecast_url).json(), required=("time_tag", "kp", "observed"))
        except Exception as error:
            forecast_error = str(error)
            _log.warning("SWPC Kp forecast endpoint unavailable: %s", error)

        newest = max((t for t in (_parse_time(r.get("time_tag")) for r in observed) if t is not None), default=None)
        if newest is None:
            raise AdapterUnavailable("SWPC Kp observed records carry no parseable time_tag")
        return [
            RunCandidate(
                provider_run_id=f"swpc-kp-{newest.strftime('%Y%m%d%H%M')}",
                run_time=newest,
                urls=[self._observed_url, self._forecast_url],
                detail={"observed": observed, "forecast": forecast, "forecast_error": forecast_error},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        observed = candidate.detail.get("observed") or []
        forecast = candidate.detail.get("forecast") or []
        if not observed:
            raise AdapterUnavailable("SWPC Kp fetch carried no observed records")

        retrieved_at = datetime.now(UTC)
        artifacts: list[Artifact] = []
        notes: list[str] = []
        complete = True

        def provenance(quality: dict[str, Any], coverage: dict[str, Any], product: str) -> dict[str, Any]:
            return {
                "source_id": self.source_id,
                "producer": "NOAA Space Weather Prediction Center",
                "product": product,
                "native_resolution": "planetary index (no spatial resolution)",
                "native_crs": "not_applicable",
                "adapter_version": self.adapter_version,
                "quality": quality,
                "coverage": coverage,
                # The planetary indices as SWPC issued them.
                **declared_classes(["retrieved"]),
            }

        observed_rows = sorted(
            ((t, r) for t, r in (((_parse_time(r.get("time_tag"))), r) for r in observed) if t is not None),
            key=lambda item: item[0],
        )
        times = [t for t, _ in observed_rows]
        kp_values = numpy.array([_float_or_nan(r.get("Kp")) for _, r in observed_rows])
        a_values = numpy.array([_float_or_nan(r.get("a_running")) for _, r in observed_rows])
        dataset = _series_dataset(
            times,
            {
                "kp_index": (kp_values, {"units": "dimensionless", "original_units": "Kp index", "long_name": "planetary K index, 3-hourly, as retrieved"}),
                "a_running": (a_values, {"units": "dimensionless", "original_units": "a index", "long_name": "running a index, as retrieved"}),
            },
            {"source": "SWPC planetary K index (observed series)"},
        )
        quality, coverage = _series_quality("kp_index", kp_values)
        observed_path = workdir / "swpc_kp_observed.zarr.zip"
        write_zarr(dataset, observed_path)
        artifacts.append(Artifact("kp_observed", MEDIA_ZARR, observed_path, provenance(quality, coverage, "Planetary K index (observed)")))
        notes.append(f"{len(times)} observed Kp records")
        complete = complete and quality["status"] == "passed"

        forecast_rows = sorted(
            ((t, r) for t, r in (((_parse_time(r.get("time_tag"))), r) for r in forecast) if t is not None),
            key=lambda item: item[0],
        )
        if forecast_rows:
            f_times = [t for t, _ in forecast_rows]
            f_values = numpy.array([_float_or_nan(r.get("kp")) for _, r in forecast_rows])
            statuses = numpy.array([
                float(_KP_STATUS_CODE.get(str(r.get("observed", "")).strip().lower(), numpy.nan)) for _, r in forecast_rows
            ])
            f_dataset = _series_dataset(
                f_times,
                {
                    "kp_index": (f_values, {"units": "dimensionless", "original_units": "Kp index", "long_name": "planetary K index outlook, as retrieved; see kp_status per value"}),
                    "kp_status": (statuses, {"units": "flag", "original_units": "provider status string", "flag_values": KP_STATUS_VALUES, "flag_meanings": KP_STATUS_MEANINGS}),
                },
                {"source": "SWPC planetary K index forecast; per-value status is the provider's own"},
            )
            f_quality, f_coverage = _series_quality("kp_index", f_values)
            forecast_path = workdir / "swpc_kp_forecast.zarr.zip"
            write_zarr(f_dataset, forecast_path)
            artifacts.append(Artifact("kp_forecast", MEDIA_ZARR, forecast_path, provenance(f_quality, f_coverage, "Planetary K index (3-day outlook, per-value status)")))
            notes.append(f"{len(f_times)} forecast Kp records with provider status")
        else:
            reason = candidate.detail.get("forecast_error") or "forecast feed returned no records"
            notes.append(f"no kp_forecast artifact: {reason}")
            complete = False

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=retrieved_at,
            complete=complete,
            qc_passed=True,
            artifacts=artifacts,
            native_crs=None,
            notes="; ".join(notes),
        )


class SWPCSolarWindAdapter:
    """The SWPC real-time solar wind magnetometer series (1-minute)."""

    source_id = "noaa-swpc-rtsw"
    adapter_version = "swpc-rtsw-v1"

    def __init__(self, client: PoliteClient | None = None, url: str = RTSW_MAG_URL) -> None:
        self._client = client
        self._url = url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            records = _records(client.get(self._url).json(), required=("time_tag", "bz_gsm"))
        except Exception as error:
            raise AdapterUnavailable(f"SWPC RTSW endpoint unavailable: {error}") from error
        if not records:
            raise AdapterUnavailable("SWPC RTSW returned no magnetometer records")
        newest = max((t for t in (_parse_time(r.get("time_tag")) for r in records) if t is not None), default=None)
        if newest is None:
            raise AdapterUnavailable("SWPC RTSW records carry no parseable time_tag")
        return [
            RunCandidate(
                provider_run_id=f"swpc-rtsw-{newest.strftime('%Y%m%d%H%M')}",
                run_time=newest,
                urls=[self._url],
                detail={"records": records},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        records = candidate.detail.get("records") or []
        if not records:
            raise AdapterUnavailable("SWPC RTSW fetch carried no records")
        rows = sorted(
            ((t, r) for t, r in (((_parse_time(r.get("time_tag"))), r) for r in records) if t is not None),
            key=lambda item: item[0],
        )
        if not rows:
            raise AdapterUnavailable("SWPC RTSW records carry no parseable time_tag")
        times = [t for t, _ in rows]
        bz = numpy.array([_float_or_nan(r.get("bz_gsm")) for _, r in rows])
        bt = numpy.array([_float_or_nan(r.get("bt")) for _, r in rows])
        # The measuring spacecraft is whatever the feed itself declares.
        sources = sorted({str(r.get("source")) for _, r in rows if r.get("source")})
        dataset = _series_dataset(
            times,
            {
                "bz_gsm": (bz, {"units": "nT", "original_units": "nT", "long_name": "interplanetary magnetic field Bz, GSM, as retrieved"}),
                "bt": (bt, {"units": "nT", "original_units": "nT", "long_name": "interplanetary magnetic field total, as retrieved"}),
            },
            {"source": "SWPC real-time solar wind (magnetometer)", "feed_declared_spacecraft": ", ".join(sources) or "undeclared"},
        )
        quality, coverage = _series_quality("bz_gsm", bz)
        path = workdir / "swpc_rtsw_mag.zarr.zip"
        write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA Space Weather Prediction Center",
            "product": "Real-time solar wind magnetic field (1-minute)",
            "native_resolution": "L1 point measurement (no spatial resolution)",
            "native_crs": "not_applicable",
            "adapter_version": self.adapter_version,
            "quality": quality,
            "coverage": coverage,
            **declared_classes(["retrieved"]),
            "feed_declared_spacecraft": ", ".join(sources) or "undeclared",
        }
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=quality["status"] == "passed",
            qc_passed=True,
            artifacts=[Artifact("solar_wind", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} 1-minute magnetometer records; spacecraft per feed: {', '.join(sources) or 'undeclared'}",
        )


class SWPCOvationAdapter:
    """The OVATION aurora probability nowcast grid, cropped to the context box."""

    source_id = "noaa-swpc-ovation"
    adapter_version = "swpc-ovation-v1"

    def __init__(self, client: PoliteClient | None = None, url: str = OVATION_URL, bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS) -> None:
        self._client = client
        self._url = url
        self._bounds = dict(bounds)

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            payload = client.get(self._url).json()
        except Exception as error:
            raise AdapterUnavailable(f"SWPC OVATION endpoint unavailable: {error}") from error
        if not isinstance(payload, dict):
            raise AdapterUnavailable("SWPC OVATION returned a non-object payload")
        observation = _parse_time(payload.get("Observation Time"))
        forecast = _parse_time(payload.get("Forecast Time"))
        if observation is None or forecast is None:
            # A nowcast without its own timestamps is not evidence.
            raise AdapterUnavailable("SWPC OVATION payload lacks Observation Time or Forecast Time; refused rather than wall-clock stamped")
        coordinates = payload.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise AdapterUnavailable("SWPC OVATION payload carries no coordinates")
        return [
            RunCandidate(
                provider_run_id=f"swpc-ovation-{observation.strftime('%Y%m%d%H%M')}",
                run_time=observation,
                urls=[self._url],
                detail={"payload": payload, "observation": observation, "forecast": forecast},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        observation: datetime | None = candidate.detail.get("observation")
        forecast: datetime | None = candidate.detail.get("forecast")
        if not isinstance(payload, dict) or observation is None or forecast is None:
            raise AdapterUnavailable("SWPC OVATION fetch carried no payload")
        coordinates = payload.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise AdapterUnavailable("SWPC OVATION payload carries no coordinates")

        south, north = self._bounds["south"], self._bounds["north"]
        west, east = self._bounds["west"], self._bounds["east"]
        cells: dict[tuple[float, float], float] = {}
        for entry in coordinates:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            lon_raw, lat_raw, value = entry[0], entry[1], entry[2]
            try:
                lon = float(lon_raw)
                lat = float(lat_raw)
                probability = float(value)
            except (TypeError, ValueError):
                continue
            if lon > 180.0:
                lon -= 360.0
            if south <= lat <= north and west <= lon <= east:
                cells[(lat, lon)] = probability
        if not cells:
            raise AdapterUnavailable("SWPC OVATION grid carries no cell inside the context box")

        latitudes = numpy.array(sorted({lat for lat, _ in cells}))
        longitudes = numpy.array(sorted({lon for _, lon in cells}))
        grid = numpy.full((1, latitudes.size, longitudes.size), numpy.nan)
        lat_index = {v: i for i, v in enumerate(latitudes)}
        lon_index = {v: i for i, v in enumerate(longitudes)}
        for (lat, lon), probability in cells.items():
            grid[0, lat_index[lat], lon_index[lon]] = probability

        stamps = numpy.array([numpy.datetime64(forecast.replace(tzinfo=None), "ns")])
        dataset = xarray.Dataset(
            {
                "aurora_probability": (
                    ("valid_time", "latitude", "longitude"),
                    grid,
                    {"units": "percent", "original_units": "percent", "long_name": "OVATION probability of visible aurora, as retrieved"},
                )
            },
            coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
            attrs={
                "source": "SWPC OVATION aurora nowcast",
                "observation_time": observation.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "forecast_time": forecast.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "model_disclosure": "OVATION model output, a nowcast ~30-40 minutes past its observation instant; not an observation",
            },
        )
        finite = float(numpy.isfinite(grid).mean())
        quality = {
            "status": "passed" if finite > 0.5 else "suspect",
            "flags": [] if finite > 0.5 else ["sparse_grid"],
            "detail": f"aurora_probability: {finite:.4f} of context-box cells carry a value; valid at the file's own Forecast Time",
        }
        coverage = {"status": "complete" if finite > 0.5 else "partial", "fraction": round(finite, 4)}

        path = workdir / "swpc_ovation.zarr.zip"
        write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA Space Weather Prediction Center",
            "product": "OVATION aurora probability nowcast",
            "native_resolution": "1 deg lat x 1 deg lon (as served)",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": quality,
            "coverage": coverage,
            **declared_classes(["retrieved"]),
            "observation_time": observation.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_disclosure": "OVATION model output; a nowcast, not an observation",
        }
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=observation,
            retrieved_at=datetime.now(UTC),
            complete=finite > 0.5,
            qc_passed=True,
            artifacts=[Artifact("aurora_grid", MEDIA_ZARR, path, provenance)],
            native_crs="EPSG:4326",
            notes=f"OVATION grid {latitudes.size}x{longitudes.size} cells, forecast instant {forecast.isoformat()}",
        )


KP_ADAPTER = register(SWPCKpAdapter())
RTSW_ADAPTER = register(SWPCSolarWindAdapter())
OVATION_ADAPTER = register(SWPCOvationAdapter())
