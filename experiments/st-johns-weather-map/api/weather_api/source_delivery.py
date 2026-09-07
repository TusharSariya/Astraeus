"""Small source read seam over existing source-local demand coordinators.

Descriptors perform no provider I/O. Results keep the existing EvidenceField
model. No transport, decoder, cadence or acquisition cache is shared here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from ingest.contract import RunCandidate

from .models import EvidenceField
from .source_contract import SourceCapability, SourceConfiguration, SourceReadingIdentity, SourceVariant
from .source_status import latest_configuration, observed_read
from .swob_delivery import SWOBPointReader


@dataclass(frozen=True)
class NativeFrame:
    valid_time: datetime
    run_id: str = "latest"
    run_time: datetime | None = None


@dataclass(frozen=True)
class NativePlan:
    frames: tuple[NativeFrame, ...]
    runs: tuple[RunCandidate, ...] = ()
    reason: str = "This native reader does not expose a selectable run inventory"


class SourceReader(Protocol):
    source_id: str
    product_id: str

    def descriptors(self) -> tuple[SourceCapability, ...]: ...
    def read_point(self, latitude: float, longitude: float, selected: datetime, *, run: str = "latest", refresh: bool = False) -> tuple[EvidenceField, ...]: ...
    def plan_series(self, start: datetime, end: datetime, *, run: str = "latest") -> NativePlan | None: ...


def reading_identity(field: EvidenceField, product_id: str) -> SourceReadingIdentity:
    from registry import fields as catalogue
    provenance = field.provenance
    ensemble = provenance.ensemble
    if provenance.member is not None:
        variant = SourceVariant(kind="member", member=provenance.member)
    elif ensemble is not None and ensemble.statistic is not None:
        variant = SourceVariant(kind="derived_statistic" if ensemble.computed_here else "provider_statistic",
            statistic=ensemble.statistic, quantile=ensemble.quantile, threshold=ensemble.threshold,
            comparison=ensemble.comparison)
    else:
        variant = SourceVariant(kind="observation" if provenance.native_report is not None else "deterministic" if provenance.run_time is not None else "unknown")
    definition = catalogue.field(field.key) if field.key is not None else None
    level = definition.level if definition is not None and not definition.is_profile else provenance.vertical_level
    return SourceReadingIdentity(source_id=provenance.source_id, product_id=product_id,
        field=field.key or field.field, variant=variant, level=level, native_level=provenance.vertical_level,
        run_time=provenance.run_time, valid_time=provenance.valid_time,
        station_id=provenance.native_report.station_id if provenance.native_report else None,
        sampled_latitude=provenance.sampled_latitude, sampled_longitude=provenance.sampled_longitude,
        artifact_revision=provenance.artifact_revision)


class ForecastSource:
    def __init__(self, source_id: str, product_id: str, factory: Callable, fields: tuple[str, ...], *, named_runs: bool):
        self.source_id, self.product_id, self.factory = source_id, product_id, factory
        self.fields, self.named_runs = fields, named_runs

    def descriptors(self):
        from registry import fields as catalogue
        return tuple(SourceCapability(source_id=self.source_id, product_id=self.product_id,
            field=key, variants=[SourceVariant(kind="deterministic")],
            levels=[str(catalogue.field(key).level)], point=True, point_product=self.product_id.upper(), native_series=True,
            run_selection="latest_previous" if self.named_runs else "latest",
            time_semantics="Provider-native forecast frames; ordinary point reads retain the source's existing matching rule",
            coverage_description="Existing Avalon point bounds; actual field and time coverage is established only by retrieval") for key in self.fields)

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run="latest", refresh=False):
        coordinator = self.factory()
        options = {}
        if run != "latest" and callable(getattr(coordinator, "run_inventory", None)):
            options["run_id"] = run
        elif run != "latest":
            from .native_runs import RunUnavailable
            raise RunUnavailable("This source cannot pin the requested run")
        if refresh:
            options["refresh"] = True
        values, _consensus, _sources = coordinator.point_fields(latitude, longitude, selected, **options)
        return tuple(value.model_copy(deep=True) for value in values if value.provenance.source_id == self.source_id)

    @observed_read
    def plan_series(self, start, end, *, run="latest"):
        from .native_runs import RunUnavailable
        coordinator = self.factory()
        if callable(getattr(coordinator, "run_inventory", None)):
            candidates = coordinator.run_inventory()
            if run != "latest" and run not in {item.provider_run_id for item in candidates}:
                raise RunUnavailable("Run no longer available in the bounded latest/previous inventory")
            frames = {}
            for candidate in candidates:
                if run not in ("latest", candidate.provider_run_id):
                    continue
                for stamp in coordinator.run_times(candidate.provider_run_id):
                    if start <= stamp < end:
                        frames.setdefault(stamp, NativeFrame(stamp, candidate.provider_run_id, candidate.run_time))
            return NativePlan(tuple(frames[stamp] for stamp in sorted(frames)), tuple(candidates),
                "Latest/previous from bounded native source discovery; listed frames are validated on acquisition")
        if run != "latest":
            raise RunUnavailable("This source cannot pin the requested run")
        stamps = coordinator.timeline_times(start)
        if self.source_id == "noaa-gfs":
            stamps, _receipt = stamps
        return NativePlan(tuple(NativeFrame(stamp) for stamp in sorted(set(stamps)) if start <= stamp < end))


class AQHISource:
    source_id = "eccc-aqhi"
    product_id = "aqhi-observations"

    def __init__(self, factory):
        self.factory = factory

    def descriptors(self):
        return (SourceCapability(source_id=self.source_id, product_id=self.product_id,
            field="air_quality_health_index", variants=[SourceVariant(kind="observation")],
            levels=["station"], point=True, native_series=False, run_selection="not_applicable",
            time_semantics="Nearest applicable native station observation at or before selection, strictly less than one hour old",
            coverage_description="Accepted Avalon station box and existing distance ceiling; no archive or forecast promise"),)

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run="latest", refresh=False):
        if run != "latest":
            from .native_runs import RunUnavailable
            raise RunUnavailable("AQHI observations have no forecast run selection")
        options = {"refresh": True} if refresh else {}
        return (self.factory().point_field(latitude, longitude, selected, **options).model_copy(deep=True),)

    def plan_series(self, start, end, *, run="latest"):
        return None


class CAMSAODSource:
    source_id = "openmeteo-cams-aod"
    product_id = "cams-global-aod"

    def __init__(self, factory):
        self.factory = factory

    def descriptors(self):
        from registry import fields as catalogue
        key = "aerosol_optical_depth_550nm"
        return (SourceCapability(source_id=self.source_id, product_id=self.product_id, field=key,
            variants=[SourceVariant(kind="deterministic")], levels=[str(catalogue.field(key).level)],
            point=True, point_product="CAMS AOD", native_series=False, run_selection="not_applicable",
            time_semantics="Exact hourly labels returned by Open-Meteo; these are reprocessed from native three-hourly CAMS data and do not identify a producer run",
            coverage_description="Selected point only, with the returned intermediary cell and missing values preserved; no primary or derived evidence admission"),)

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run="latest", refresh=False):
        if run != "latest":
            from .native_runs import RunUnavailable
            raise RunUnavailable("CAMS intermediary values do not expose selectable producer runs")
        return tuple(field.model_copy(deep=True) for field in self.factory().point_fields(
            latitude, longitude, selected, refresh=refresh))

    def plan_series(self, start, end, *, run="latest"):
        return None


class SWOBSource(SWOBPointReader):
    def descriptors(self):
        from registry import fields as catalogue
        keys = ("temperature_2m", "dew_point_2m", "relative_humidity_2m", "mean_sea_level_pressure",
                "wind_speed_10m", "wind_direction_10m")
        return tuple(SourceCapability(source_id=self.source_id, product_id=self.product_id, field=key,
            variants=[SourceVariant(kind="observation")], levels=[str(catalogue.field(key).level)],
            point=True, point_product="SWOB", native_series=False, run_selection="not_applicable",
            time_semantics="Exact native station report time; no synthetic cadence or archive inventory",
            coverage_description="Existing bounded MSC station selection; native gaps and QC remain") for key in keys)


class ECMWFSource(ForecastSource):
    def descriptors(self):
        return tuple(capability.model_copy(update={"point_product": "IFS" if self.source_id == "ecmwf-ifs" else "AIFS Single",
            "native_series": False, "run_selection": "latest",
            "time_semantics": "Exact published deterministic native frame; no interpolation or ensemble substitution"})
            for capability in super().descriptors())

    def plan_series(self, start, end, *, run="latest"):
        return None


class GEFSSource:
    source_id, product_id = "noaa-gefs", "pgrb2ap5"

    def __init__(self, factory):
        self.factory = factory

    def descriptors(self):
        from .gefs_delivery import point_capabilities
        return point_capabilities()

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run="latest", refresh=False, variant=None, member_filter=None):
        from .native_runs import RunUnavailable
        if run != "latest" or (variant is not None and variant.kind not in ("member", "derived_statistic")):
            raise RunUnavailable("GEFS supports a selected lead and explicit member or locally derived statistic")
        options = {"refresh": True} if refresh else {}
        if member_filter is not None:
            options["member"] = member_filter
        if variant is not None:
            if variant.kind == "member":
                options["member"] = variant.member
            else:
                options.update(statistic=variant.statistic, quantile=variant.quantile,
                               threshold=variant.threshold, comparison=variant.comparison)
        fields, _consensus, _sources = self.factory().point_fields(latitude, longitude, selected, **options)
        return tuple(field.model_copy(deep=True) for field in fields)

    def plan_series(self, start, end, *, run="latest"):
        return None


def source_readers() -> dict[str, SourceReader]:
    # Lazy imports preserve existing monkeypatch seams and do not create clients
    # when the catalogue is read. Fields here name implemented delivery paths,
    # independently from the broader catalogue of published provider fields.
    from .hrdps_query import hrdps_query_coordinator
    from .rdps_query import rdps_query_coordinator
    from .gdps_query import gdps_query_coordinator
    from .gfs_query import gfs_query_coordinator
    from .aqhi_query import aqhi_query_service
    from .openmeteo_cams_aod_query import openmeteo_cams_aod_query_service
    from .swob_query import swob_query_service
    from .gefs_query import gefs_query_coordinator
    from .ecmwf_query import ecmwf_query_coordinator
    common = ("temperature_2m", "dew_point_2m", "relative_humidity_2m", "wind_u_10m", "wind_v_10m", "mean_sea_level_pressure")
    readers = [
        ForecastSource("eccc-hrdps", "hrdps", hrdps_query_coordinator, (*common, "total_cloud_opacity"), named_runs=True),
        ForecastSource("eccc-rdps", "rdps", rdps_query_coordinator, (*common, "total_cloud_opacity"), named_runs=True),
        ForecastSource("eccc-gdps", "gdps", gdps_query_coordinator, (*common, "total_cloud_opacity"), named_runs=True),
        ForecastSource("noaa-gfs", "gfs", gfs_query_coordinator, (*common, "visibility", "total_cloud_geometric", "cloud_low", "cloud_middle", "cloud_high"), named_runs=True),
        AQHISource(aqhi_query_service),
        CAMSAODSource(openmeteo_cams_aod_query_service),
        SWOBSource(swob_query_service),
        GEFSSource(gefs_query_coordinator),
        *(ECMWFSource(source_id, product_id, lambda source_id=source_id: ecmwf_query_coordinator(source_id),
            ("temperature_2m", "dew_point_2m", "relative_humidity_2m", "mean_sea_level_pressure", "total_cloud_geometric"), named_runs=False)
            for source_id, product_id in (("ecmwf-ifs", "ifs"), ("ecmwf-aifs-single", "aifs-single"))),
    ]
    return {reader.source_id: reader for reader in readers}


def source_capabilities(source_id: str) -> list[SourceCapability]:
    reader = source_readers().get(source_id)
    return list(reader.descriptors()) if reader else []


def source_configuration(source_id: str) -> SourceConfiguration:
    reported = latest_configuration(source_id)
    if reported is not None:
        return reported
    if source_id in source_readers():
        return SourceConfiguration(state="ready", reason="Anonymous source read software is available; this does not establish successful retrieval or coverage")
    return SourceConfiguration()
