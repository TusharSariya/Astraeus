"""ECCC Datamart NWP model adapters (HRDPS, RDPS, GDPS).

Walks the Apache autoindex on dd.weather.gc.ca, retrieves single-parameter GRIB2
files for the Avalon domain, decodes with cfgrib/ecCodes, crops to bounds,
normalizes units, and packages into zipped Zarr artifacts.

Two discovery facts, verified live on 2026-08-30, shape this module:

* ``dd.weather.gc.ca/today/model_hrdps/`` is empty and its ``continental/2.5km``
  child is a 404. The working layout is the dated one,
  ``/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/``. The dated directory rolls at 00Z
  and is empty for the first hours of the UTC day, so discovery tries today and
  then falls back to yesterday. Neither the ``today`` alias nor a single date
  can find a run at 02:30Z.
* The run identity is stamped in the filename
  (``20260829T18Z_MSC_HRDPS_TMP_AGL-2m_...``). Deriving it from ``window.now``
  instead — as this adapter used to — mislabels every run fetched after 00Z from
  the previous day's directory.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    AVALON_CORE_BOUNDS,
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import crop_to_bbox, normalize_units, open_grib, strip_message_scalars, write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, required_leads, validate_run
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

ECCC_DATAMART_BASE = "https://dd.weather.gc.ca"
DATED_PATH_SEGMENT = "WXO-DD"

# 20260829T18Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2
_FILE_RUN_STAMP = re.compile(r"(?P<date>\d{8})T(?P<hour>\d{2})Z")
_CYCLE_DIR = re.compile(r"^\d{2}/?$")
_LEAD_DIR = re.compile(r"^\d{3}/?$")

# ``total_cloud`` is deliberately absent from all three maps below.
#
# MSC publishes it (HRDPS ``TCDC_Sfc``, RDPS ``TotalCloudCover_Sfc``) and the
# files download fine, but the message decodes with ``paramId=0`` and
# ``shortName``, ``name``, ``cfVarName`` and ``units`` all literally
# ``'unknown'``. Verified live on 2026-08-30 against the 12Z PT006H files
# with ecCodes 2.48.0 (the ``eccodeslib`` wheel this worker image now uses;
# the earlier blame on the Debian 2.28.0 package was wrong about the cause):
#
#   centre=cwao, tablesVersion=4, localTablesVersion=1, template 4.0,
#   discipline=0, parameterCategory=6, parameterNumber=1
#   (WMO code table 4.2: "Total cloud cover", %),
#   typeOfFirstFixedSurface=1 (sfc), typeOfSecondFixedSurface=255.
#
# ecCodes' ``grib2/shortName.def`` concept ``tcc`` matches 0/6/1 only with
# ``typeOfSecondFixedSurface=8`` (top of atmosphere, i.e. a whole-column
# quantity); CWAO stamps 255 (missing), and ecCodes ships no
# ``localConcepts/cwao`` that would say otherwise. Setting the second surface
# to 8 on an otherwise identical message makes 2.48.0 name it ``tcc`` /
# ``%``, so the gap is a definitions mismatch, not a library age. The values
# span 0.0-100.0, which is what a percentage looks like, but a value range is
# an inference, not a retrieval, and this experiment does not publish a field
# whose units the decoder declines to declare. Publishing it as ``percent``
# on the strength of the WMO table entry or its range would be the invention
# the units check exists to catch, so the field is withheld pending the
# owner's decision (publish from the WMO 0/6/1 keys, or carry a local
# ecCodes definitions overlay), and the other six fields publish.

# HRDPS variable map: canonical -> (GRIB file var prefix, level token)
HRDPS_VARS = {
    "temperature_2m": ("TMP", "AGL-2m"),
    "dew_point_2m": ("DPT", "AGL-2m"),
    "relative_humidity_2m": ("RH", "AGL-2m"),
    "wind_u_10m": ("UGRD", "AGL-10m"),
    "wind_v_10m": ("VGRD", "AGL-10m"),
    "mean_sea_level_pressure": ("PRMSL", "MSL"),
}

# RDPS variable map (CamelCase upstream naming)
RDPS_VARS = {
    "temperature_2m": ("AirTemp", "AGL-2m"),
    "dew_point_2m": ("DewPoint", "AGL-2m"),
    "wind_u_10m": ("WindU", "AGL-10m"),
    "wind_v_10m": ("WindV", "AGL-10m"),
    "mean_sea_level_pressure": ("Pressure_MSL", "MSL"),
}

# GDPS variable map (CamelCase upstream naming)
GDPS_VARS = {
    "temperature_2m": ("AirTemp", "AGL-2m"),
    "dew_point_2m": ("DewPoint", "AGL-2m"),
    "wind_u_10m": ("WindU", "AGL-10m"),
    "wind_v_10m": ("WindV", "AGL-10m"),
    "mean_sea_level_pressure": ("Pressure_MSL", "MSL"),
}

# Normalized units per canonical variable, as ``ingest.grib.normalize_units``
# leaves them. A declared field arriving in anything else is a QC failure.
CANONICAL_FIELD_UNITS = {
    "temperature_2m": ("degC", "2 m"),
    "dew_point_2m": ("degC", "2 m"),
    "relative_humidity_2m": ("percent", "2 m"),
    "wind_u_10m": ("m s-1", "10 m"),
    "wind_v_10m": ("m s-1", "10 m"),
    "mean_sea_level_pressure": ("hPa", "mean sea level"),
    "total_cloud": ("percent", "column"),
}


def manifest_for(source_id: str, var_map: Mapping[str, tuple[str, str]]) -> RunManifest:
    """Every mapped variable is mandatory: the map is the adapter's own promise."""
    fields = []
    for name in var_map:
        units, level = CANONICAL_FIELD_UNITS[name]
        fields.append(RequiredField(name, units, level=level))
    return RunManifest(source_id=source_id, fields=tuple(fields))


def parse_run_stamp(filename: str) -> datetime | None:
    """Read the run's own ``{YYYYMMDD}T{HH}Z`` stamp out of a Datamart filename."""
    match = _FILE_RUN_STAMP.search(filename)
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group('date')}{match.group('hour')}", "%Y%m%d%H").replace(tzinfo=UTC)
    except ValueError:
        return None


class ECCCDataMartAdapter:
    """Ingests GRIB2 datasets from ECCC Datamart dated directory trees."""

    def __init__(
        self,
        *,
        source_id: str,
        model_subpath: str,
        grid_token: str,
        var_map: Mapping[str, tuple[str, str]],
        bounds: Mapping[str, float] = AVALON_CORE_BOUNDS,
        adapter_version: str = "eccc-datamart-v1",
        client: PoliteClient | None = None,
        base_url: str = ECCC_DATAMART_BASE,
        fallback_days: int = 1,
    ) -> None:
        self.source_id = source_id
        self.model_subpath = model_subpath
        self.grid_token = grid_token
        self.var_map = dict(var_map)
        self.bounds = dict(bounds)
        self.adapter_version = adapter_version
        self.manifest = manifest_for(source_id, self.var_map)
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._fallback_days = max(0, fallback_days)

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def model_root(self, date_str: str) -> str:
        return f"{self._base_url}/{date_str}/{DATED_PATH_SEGMENT}/{self.model_subpath}/"

    # --- discovery -------------------------------------------------------
    def _candidates_for_date(self, client: PoliteClient, date_str: str) -> list[RunCandidate]:
        root_url = self.model_root(date_str)
        try:
            entries = client.list_directory(root_url)
        except Exception as error:
            _log.info("%s: no listing at %s (%s)", self.source_id, root_url, error)
            return []

        cycles = sorted({entry.rstrip("/") for entry in entries if _CYCLE_DIR.match(entry)}, reverse=True)
        candidates: list[RunCandidate] = []
        for cycle in cycles:
            cycle_url = f"{root_url}{cycle}/"
            try:
                hour_entries = client.list_directory(cycle_url)
            except Exception:
                continue
            hours = sorted({entry.rstrip("/") for entry in hour_entries if _LEAD_DIR.match(entry)})
            if "000" not in hours:
                continue

            analysis_url = f"{cycle_url}000/"
            try:
                files = client.list_directory(analysis_url, suffixes=(".grib2",))
            except Exception:
                continue
            stamps = {parse_run_stamp(name) for name in files}
            stamps.discard(None)
            if len(stamps) != 1:
                # No stamp, or a directory mixing runs: the run cannot be named
                # honestly, and a mislabelled run is worse than a missing one.
                _log.warning("%s: %s carries %d distinct run stamps", self.source_id, analysis_url, len(stamps))
                continue
            run_dt = stamps.pop()

            candidates.append(
                RunCandidate(
                    provider_run_id=run_dt.strftime("%Y%m%d%H"),
                    run_time=run_dt,
                    urls=[cycle_url],
                    detail={
                        "cycle": cycle,
                        "date_str": date_str,
                        "cycle_url": cycle_url,
                        "available_hours": hours,
                        "run_stamp": run_dt.strftime("%Y%m%dT%HZ"),
                    },
                )
            )
        return candidates

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        tried: list[str] = []
        for day_offset in range(self._fallback_days + 1):
            date_str = (window.now - timedelta(days=day_offset)).strftime("%Y%m%d")
            tried.append(date_str)
            candidates = self._candidates_for_date(client, date_str)
            if candidates:
                return candidates
        raise AdapterUnavailable(
            f"{self.source_id}: no populated run cycle under {self._base_url}/{{{','.join(tried)}}}/{DATED_PATH_SEGMENT}/{self.model_subpath}/"
        )

    # --- retrieval -------------------------------------------------------
    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        cycle_url = candidate.detail.get("cycle_url", "")
        available_hours = candidate.detail.get("available_hours", [])
        if not cycle_url:
            raise AdapterUnavailable(f"{self.source_id}: candidate carries no cycle URL")
        run_time = candidate.run_time
        if run_time is None:
            raise AdapterUnavailable(f"{self.source_id}: candidate has no run time derived from its filenames")

        target_hours = [f"{hour:03d}" for hour in range(25) if f"{hour:03d}" in available_hours]
        if not target_hours:
            raise AdapterUnavailable(f"No target forecast hours available for {candidate.provider_run_id}")

        hourly_datasets: list[xarray.Dataset] = []
        decode_errors: list[str] = []
        retrieved_at = datetime.now(UTC)

        for hour_str in target_hours:
            valid_time = run_time + timedelta(hours=int(hour_str))
            if not window.covers(valid_time):
                continue

            hour_dir_url = f"{cycle_url}{hour_str}/"
            try:
                file_list = client.list_directory(hour_dir_url, suffixes=(".grib2",))
            except Exception as error:
                decode_errors.append(f"listing:{hour_dir_url}")
                _log.warning("Could not list %s: %s", hour_dir_url, error)
                continue

            var_datasets: dict[str, xarray.DataArray] = {}
            for canonical_name, (eccc_var, level) in self.var_map.items():
                match_file = None
                for fname in file_list:
                    if f"_{eccc_var}_" in fname and (f"_{level}_" in fname or f"_{level}." in fname or level in fname):
                        match_file = fname
                        break
                if not match_file:
                    decode_errors.append(f"absent:{canonical_name}@{hour_str}")
                    continue

                stamp = parse_run_stamp(match_file)
                if stamp is not None and stamp != run_time:
                    # The directory rolled under us mid-fetch; mixing two runs
                    # into one artifact would be an invented forecast.
                    decode_errors.append(f"run_stamp_mismatch:{match_file}")
                    continue

                file_url = f"{hour_dir_url}{match_file}"
                local_grib = workdir / f"{canonical_name}_{hour_str}.grib2"
                try:
                    client.download(file_url, local_grib, max_bytes=10 * 1024 * 1024)
                    decoded = normalize_units(crop_to_bbox(open_grib(local_grib), self.bounds))
                    data_var_names = list(decoded.data_vars)
                    if not data_var_names:
                        decode_errors.append(f"no_variable:{match_file}")
                        continue
                    # Each field arrives as its own single-message GRIB, so it
                    # carries its own scalar level coordinate (2 m for screen
                    # temperature, 10 m for wind). Those must move into attrs
                    # before the fields are filed into one Dataset below, or the
                    # merge fails on the disagreement.
                    #
                    # ``load`` is what makes the ``unlink`` below safe. cfgrib
                    # reads on demand, so everything up to here is a promise
                    # against a file this loop deletes as soon as it moves to
                    # the next field; without materialising now, the values are
                    # only fetched at write_zarr time and every run dies with
                    # FileNotFoundError. The crop already bounded this to the
                    # Avalon window, so what is held is one small field.
                    var_datasets[canonical_name] = strip_message_scalars(decoded[data_var_names[0]].load())
                except Exception as error:
                    decode_errors.append(f"decode:{match_file}")
                    _log.warning("Failed to decode %s: %s", file_url, error)
                finally:
                    local_grib.unlink(missing_ok=True)

            if not var_datasets:
                decode_errors.append(f"empty_step:{hour_str}")
                continue

            step = xarray.Dataset(var_datasets).expand_dims(
                valid_time=[numpy.datetime64(valid_time.replace(tzinfo=None), "ns")]
            )
            hourly_datasets.append(step)

        if not hourly_datasets:
            raise AdapterUnavailable(f"No GRIB2 fields could be fetched or cropped for {self.source_id}")

        combined = xarray.concat(hourly_datasets, dim="valid_time")
        manifest = RunManifest(
            source_id=self.manifest.source_id,
            fields=self.manifest.fields,
            required_valid_times=required_leads(window, run_time, max_lead_hours=int(target_hours[-1])),
            min_coverage_fraction=self.manifest.min_coverage_fraction,
            bounds=self.bounds,
        )
        validation = validate_run(manifest, combined, window=window, decode_errors=decode_errors)

        zarr_path = workdir / f"{self.source_id}.zarr.zip"
        write_zarr(combined, zarr_path)

        provenance = {
            "source_id": self.source_id,
            "producer": "Environment and Climate Change Canada",
            "product": self.source_id.upper(),
            "native_resolution": self.grid_token,
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "provider_run_stamp": candidate.detail.get("run_stamp", ""),
            "quality": validation.as_quality(),
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
            run_time=run_time,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes=f"Ingested {len(hourly_datasets)} forecast lead steps for {self.source_id}; {validation.detail}",
        )


HRDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-hrdps",
        model_subpath="model_hrdps/continental/2.5km",
        grid_token="RLatLon0.0225",
        var_map=HRDPS_VARS,
        bounds=AVALON_CORE_BOUNDS,
        adapter_version="hrdps-v2",
    )
)

RDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-rdps",
        model_subpath="model_rdps/10km",
        grid_token="RLatLon0.09",
        var_map=RDPS_VARS,
        bounds=AVALON_CORE_BOUNDS,
        adapter_version="rdps-v2",
    )
)

# GDPS is published at 10 km, not 15 km: ``today/model_gdps/15km/`` is a 404 and
# ``10km/`` is a 200, verified 2026-08-30.
GDPS_ADAPTER = register(
    ECCCDataMartAdapter(
        source_id="eccc-gdps",
        model_subpath="model_gdps/10km",
        # Directory resolution only; the exact RLatLon grid token in the
        # filenames was not verified, so it is not asserted here.
        grid_token="10km",
        var_map=GDPS_VARS,
        bounds=ATLANTIC_CONTEXT_BOUNDS,
        adapter_version="gdps-v2",
    )
)
