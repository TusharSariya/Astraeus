"""ECCC GeoMet OGC API Features adapter (SWOB surface observations).

Queries api.weather.gc.ca for real-time surface observations within the Avalon bounding
box and fetch window, extracts meteorological variables and QC flags, and packages
them into Zarr observation datasets.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import numpy
import xarray

from ingest.contract import (
    AVALON_CORE_BOUNDS,
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, validate_run
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

ECCC_OGC_BASE = "https://api.weather.gc.ca"

# SWOB is a heterogeneous station network: a marine buoy reports no dew point
# and an AWOS may report no pressure, so only temperature is mandatory. The
# station-by-time array is sparse by construction — a station absent at one
# valid time leaves a hole — so full coverage is not achievable and demanding it
# would refuse every real batch.
SWOB_MANIFEST = RunManifest(
    source_id="eccc-swob",
    fields=(
        RequiredField("temperature_2m", "degC", level="2 m"),
        RequiredField("dew_point_2m", "degC", level="2 m", optional=True),
        RequiredField("relative_humidity_2m", "percent", level="2 m", optional=True),
        RequiredField("mean_sea_level_pressure", "hPa", level="mean sea level", optional=True),
        RequiredField("wind_u_10m", "m s-1", level="10 m", optional=True),
        RequiredField("wind_v_10m", "m s-1", level="10 m", optional=True),
    ),
    # Overridden per run: see ``_coverage_floor``.
    min_coverage_fraction=0.9,
)


def _coverage_floor(observation_count: int, cell_count: int, *, tolerance: float = 0.9) -> float:
    """The coverage a fully-populated SWOB batch can actually reach.

    The artifact layout is a ``(time, latitude, longitude)`` outer product
    because that is what ``api.weather_api.store`` samples, but the stations are
    scattered points: a batch of N observations can only ever fill N of the
    ``time x lat x lon`` cells. Comparing raw grid occupancy against 1.0 would
    reject every real batch, so the threshold is that occupancy scaled by
    ``tolerance``. What the check then actually measures is the fraction of
    *received observations that carried the field* - which is the real failure
    mode - rather than the density of a grid the network never fills.
    """
    if cell_count <= 0 or observation_count <= 0:
        return 1.0
    return min(1.0, tolerance * observation_count / cell_count)


def parse_iso_time(val: Any) -> datetime | None:
    if not val:
        return None
    text = str(val).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        return None


def parse_wind_uv(speed_ms: float | None, wdir_deg: float | None) -> tuple[float | None, float | None]:
    if speed_ms is None or wdir_deg is None:
        return None, None
    rad = math.radians(wdir_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return round(u, 2), round(v, 2)


class ECCCOGCSWOBAdapter:
    """Ingests surface observations from the ECCC GeoMet SWOB collection."""

    source_id = "eccc-swob"
    adapter_version = "eccc-ogc-swob-v1"

    def __init__(
        self,
        *,
        base_url: str = ECCC_OGC_BASE,
        collection: str = "swob-realtime",
        bounds: Mapping[str, float] = AVALON_CORE_BOUNDS,
        client: PoliteClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._collection = collection
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def _build_url(self, window: FetchWindow) -> str:
        bbox_str = f"{self._bounds['west']},{self._bounds['south']},{self._bounds['east']},{self._bounds['north']}"
        start_iso = window.start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = window.end.strftime("%Y-%m-%dT%H:%M:%SZ")
        datetime_param = f"{start_iso}/{end_iso}"
        return f"{self._base_url}/collections/{self._collection}/items?bbox={bbox_str}&datetime={quote(datetime_param, safe='/:')}&limit=1000&f=json"

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        url = self._build_url(window)
        try:
            resp = client.get(url)
            data = resp.json()
        except Exception as error:
            raise AdapterUnavailable(f"ECCC OGC API unavailable for {self.source_id}: {error}") from error

        features = data.get("features", [])
        if not features:
            raise AdapterUnavailable(f"No SWOB observations returned for Avalon bbox in window {window.start}..{window.end}")

        # Find newest timestamp among features
        latest_time = None
        for feat in features:
            props = feat.get("properties", {})
            dt = parse_iso_time(props.get("date_tm-value") or props.get("date_tm"))
            if dt and (latest_time is None or dt > latest_time):
                latest_time = dt

        run_time = latest_time or window.now
        run_id = f"swob-{int(run_time.timestamp())}"

        return [
            RunCandidate(
                provider_run_id=run_id,
                run_time=run_time,
                urls=[url],
                detail={"features": features, "query_url": url},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        features = candidate.detail.get("features", [])
        if not features:
            client = self._get_client()
            url = candidate.detail.get("query_url") or self._build_url(window)
            try:
                features = client.get(url).json().get("features", [])
            except Exception as error:
                raise AdapterUnavailable(f"Failed fetching SWOB features: {error}") from error

        # Group observations by (station_name, lat, lon) and valid_time
        stations: dict[str, tuple[float, float]] = {}
        observations: dict[tuple[datetime, str], dict[str, Any]] = {}
        qc_flags: set[str] = set()

        for feat in features:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates")
            if not coords or len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            props = feat.get("properties", {})

            stn_name = str(props.get("stn_nam-value") or props.get("stn_nam") or f"{lat:.2f},{lon:.2f}")
            stations[stn_name] = (lat, lon)

            dt = parse_iso_time(props.get("date_tm-value") or props.get("date_tm"))
            if not dt or not window.covers(dt):
                continue

            # Extract QC flags
            for k, v in props.items():
                if ("-qa" in k or "-data_flag" in k) and v is not None and v != "":
                    qc_flags.add(f"{k}:{v}")

            t_val = props.get("air_temp")
            d_val = props.get("dwpt_temp")
            rh_val = props.get("rel_hum")
            p_val = props.get("mslp")
            w_spd = props.get("wnd_spd")
            w_dir = props.get("wnd_dir")

            obs_data: dict[str, Any] = {
                "lat": lat,
                "lon": lon,
                "t": float(t_val) if t_val is not None else None,
                "td": float(d_val) if d_val is not None else None,
                "rh": float(rh_val) if rh_val is not None else None,
                "p": float(p_val) if p_val is not None else None,
                "w_spd": float(w_spd) if w_spd is not None else None,
                "w_dir": float(w_dir) if w_dir is not None else None,
            }
            observations[(dt, stn_name)] = obs_data

        if not observations:
            raise AdapterUnavailable(f"No valid observations inside window for {self.source_id}")

        # Build grid coordinates: sorted unique valid times, latitudes, longitudes
        unique_times = sorted({t for t, _ in observations.keys()})
        unique_lats = sorted({lat for lat, _ in stations.values()})
        unique_lons = sorted({lon for _, lon in stations.values()})

        n_t = len(unique_times)
        n_lat = len(unique_lats)
        n_lon = len(unique_lons)

        lat_map = {lat: i for i, lat in enumerate(unique_lats)}
        lon_map = {lon: j for j, lon in enumerate(unique_lons)}
        time_map = {t: k for k, t in enumerate(unique_times)}

        temp_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")
        dewp_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")
        rh_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")
        pres_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")
        wind_u_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")
        wind_v_arr = numpy.full((n_t, n_lat, n_lon), numpy.nan, dtype="float64")

        for (dt, stn_name), obs in observations.items():
            t_idx = time_map[dt]
            lat_idx = lat_map[obs["lat"]]
            lon_idx = lon_map[obs["lon"]]

            if obs["t"] is not None:
                temp_arr[t_idx, lat_idx, lon_idx] = obs["t"]
            if obs["td"] is not None:
                dewp_arr[t_idx, lat_idx, lon_idx] = obs["td"]
            if obs["rh"] is not None:
                rh_arr[t_idx, lat_idx, lon_idx] = obs["rh"]
            if obs["p"] is not None:
                pres_arr[t_idx, lat_idx, lon_idx] = obs["p"]

            u, v = parse_wind_uv(obs["w_spd"], obs["w_dir"])
            if u is not None and v is not None:
                wind_u_arr[t_idx, lat_idx, lon_idx] = u
                wind_v_arr[t_idx, lat_idx, lon_idx] = v

        stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in unique_times])
        lats = numpy.array(unique_lats, dtype="float64")
        lons = numpy.array(unique_lons, dtype="float64")

        dataset = xarray.Dataset(
            {
                "temperature_2m": (("valid_time", "latitude", "longitude"), temp_arr, {"units": "degC", "original_units": "degC"}),
                "dew_point_2m": (("valid_time", "latitude", "longitude"), dewp_arr, {"units": "degC", "original_units": "degC"}),
                "relative_humidity_2m": (("valid_time", "latitude", "longitude"), rh_arr, {"units": "percent", "original_units": "percent"}),
                "mean_sea_level_pressure": (("valid_time", "latitude", "longitude"), pres_arr, {"units": "hPa", "original_units": "hPa"}),
                "wind_u_10m": (("valid_time", "latitude", "longitude"), wind_u_arr, {"units": "m s-1", "original_units": "m s-1"}),
                "wind_v_10m": (("valid_time", "latitude", "longitude"), wind_v_arr, {"units": "m s-1", "original_units": "m s-1"}),
            },
            coords={"valid_time": stamps, "latitude": lats, "longitude": lons},
            attrs={"source": "ECCC SWOB Realtime OGC API", "station_count": len(stations)},
        )

        # A QC flag the provider marks failed or rejected is the provider telling
        # us the value is wrong; it is passed in as a decode error so the run
        # cannot publish as clean.
        rejected = sorted(flag for flag in qc_flags if "fail" in flag.lower() or "reject" in flag.lower())
        manifest = RunManifest(
            source_id=SWOB_MANIFEST.source_id,
            fields=SWOB_MANIFEST.fields,
            min_coverage_fraction=_coverage_floor(len(observations), n_t * n_lat * n_lon),
            bounds=self._bounds,
        )
        validation = validate_run(manifest, dataset, window=window, decode_errors=[f"qc:{flag}" for flag in rejected])

        zarr_path = workdir / "eccc_swob.zarr.zip"
        write_zarr(dataset, zarr_path)

        provenance = {
            "source_id": self.source_id,
            "producer": "Environment and Climate Change Canada",
            "product": "Surface Weather Observations (SWOB-ML Realtime)",
            "native_resolution": "in-situ station network",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": {**validation.as_quality(), "provider_flags": sorted(qc_flags)[:50]},
            "coverage": validation.as_coverage(),
        }

        artifact = Artifact(
            logical_name="surface",
            media_type=MEDIA_ZARR,
            payload_path=zarr_path,
            provenance=provenance,
        )

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=unique_times[-1],
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=f"Ingested {len(observations)} SWOB observation points across {len(stations)} stations; {validation.detail}",
        )


SWOB_ADAPTER = register(ECCCOGCSWOBAdapter())
