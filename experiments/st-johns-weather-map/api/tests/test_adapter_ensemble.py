"""Ensemble access shapes, strict failures, and retained live readback.

Every family here is declared **not schedulable**, so none of these adapters has
run through the scheduler. Fixtures pin identifiers, request shapes, assembly,
storage scope, and failure behavior. The REPS test also builds a member
artifact from those fixtures and reads it through the experimental HTTP API
without making the source operational. The 2026-09-05 live capture is evidenced
by a hand-trimmed receipt, not by a retained payload (owner decision of
2026-09-05, issue 70).

Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/artifact-ingestion/spec.md
"""

from __future__ import annotations

import importlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest
import xarray
import zarr
from fastapi.testclient import TestClient
from ingest.adapters import eccc_geomet_ensemble as reps_module
from ingest.adapters.eccc_geomet_ensemble import (
    REPS_EVIDENCE_BOX,
    REPS_SCALESIZE,
    ECCCREPSEnsembleAdapter,
    REPSCoverageError,
    control_retrieval_for,
    coverage_id,
    coverage_params,
    coverage_url,
    declaration_for,
    decode_reps_geotiff,
    member_identifiers,
    pressure_coverage_id,
    stored_member_coverages,
)
from ingest.adapters.eccc_geomet_reductions import (
    SELECTED_REDUCTIONS,
    fetch_geps_reductions,
)
from ingest.adapters.ecmwf_opendata import (
    ECMWFAIFSEnsembleAdapter,
    ECMWFENSEnsembleAdapter,
    IFS_CYCLE_50R1_CONTROL_MAPPING,
    MAX_MAPPED_CONTROL_DISCOVERY_REQUESTS,
    _download_verified_range,
    family_upstream_params,
    parse_ecmwf_index_records,
    select_member_ranges,
)
from ingest.adapters.noaa_s3 import (
    NOAAGEFSEnsembleAdapter,
    gefs_member_identifiers,
    select_gefs_member_records,
)
from ingest.contract import AdapterUnavailable, FetchWindow, RunCandidate
from ingest.grib import CONTROL_COORD, MEMBER_DIM
from ingest.registry import get_config, registered_adapters
from ingest.store import CurrentArtifact, _declared_valid_time_nanoseconds
from PIL import Image, TiffImagePlugin
from weather_api import store as api_store
from weather_api.app import app
from weather_api.store import LiveStore

#: The four families this task builds, in the owner's declared build order.
BUILD_ORDER = ("eccc-reps", "ecmwf-aifs-ens", "ecmwf-ens", "noaa-gefs")
api_module = importlib.import_module("weather_api.app")


# --------------------------------------------------------------------- fixtures


def member_field(units: str, *, value: float = 50.0) -> xarray.DataArray:
    """One member's field over a tiny box, in the normalized unit.

    Stands in for a decoded GRIB message or GeoTIFF coverage: what the adapters
    do with it - stack it onto the member axis, stamp a window on it, judge its
    units - does not depend on how it was decoded.
    """
    return xarray.DataArray(
        numpy.full((2, 3), value, dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [47.0, 48.0], "longitude": [-53.0, -52.0, -51.0]},
        attrs={"units": units},
    )


UNITS_BY_KEY = {
    "total_cloud_opacity": "percent",
    "total_cloud_geometric": "percent",
    "total_cloud_mean_6h": "percent",
    "wind_speed_10m": "m s-1",
    "temperature_2m": "degC",
    "dew_point_2m": "degC",
    "relative_humidity_2m": "percent",
    "specific_humidity_2m": "kg kg-1",
    "downward_shortwave_accumulated": "J m-2",
    "mean_sea_level_pressure": "hPa",
    "wind_u_10m": "m s-1",
    "wind_v_10m": "m s-1",
    "cloud_low": "percent",
    "cloud_middle": "percent",
    "cloud_high": "percent",
}


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.status_code = 200
        self.headers = {"Content-Type": "image/tiff"}
        self.text = content.decode("utf-8", "replace")


class FakeClient:
    """A PoliteClient stand-in that answers from strings, and records every URL.

    Nothing here touches the network. ``texts`` answers ``.idx`` and ``.index``
    lookups by exact URL, ``missing`` makes a URL raise the way a 404 would, and
    every range download writes a stub the injected reader never opens.
    """

    def __init__(
        self, *, texts: dict[str, str] | None = None, missing: tuple[str, ...] = ()
    ) -> None:
        self.texts = texts or {}
        self.missing = missing
        self.urls: list[str] = []
        self.ranges: list[tuple[str, list]] = []

    def _check(self, url: str) -> None:
        for fragment in self.missing:
            if fragment in url:
                raise FileNotFoundError(f"404 {url}")

    def get(self, url: str, **_kwargs) -> FakeResponse:
        self.urls.append(url)
        self._check(url)
        return FakeResponse(b"II*\x00fake-tiff")

    def get_bytes(self, url: str, *, max_bytes: int):
        response = self.get(url)
        assert len(response.content) <= max_bytes
        return response.content, response.headers

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        self._check(url)
        if url in self.texts:
            return self.texts[url]
        raise FileNotFoundError(f"no fixture text for {url}")

    def download_ranges(
        self, url: str, destination: Path, ranges, *, max_bytes: int
    ) -> int:
        self.urls.append(url)
        self._check(url)
        self.ranges.append((url, list(ranges)))
        destination.write_bytes(b"GRIB-stub")
        return sum(end - start + 1 for start, end in self.ranges[-1][1])


def window_at(moment: datetime = datetime(2026, 9, 2, 12, tzinfo=UTC)) -> FetchWindow:
    return FetchWindow(now=moment)


def open_artifact(payload_path: Path) -> xarray.Dataset:
    """The staged artifact, read back the way the store reads it."""
    return xarray.open_zarr(
        zarr.storage.ZipStore(str(payload_path), mode="r"), consolidated=False
    )


# ------------------------------------------------- build order and registration


def test_the_four_ensemble_adapters_are_registered_in_the_declared_build_order():
    adapters = registered_adapters()
    names = [type(adapters[source_id]).__name__ for source_id in BUILD_ORDER]
    assert names == [
        "ECCCREPSEnsembleAdapter",
        "ECMWFAIFSEnsembleAdapter",
        "ECMWFENSEnsembleAdapter",
        "NOAAGEFSEnsembleAdapter",
    ]
    # The order is the registry's, not this test's: build order 1 to 4.
    orders = [get_config(source_id).ensemble.build_order for source_id in BUILD_ORDER]
    assert orders == [1, 2, 3, 4]


def test_registering_an_ensemble_adapter_does_not_make_the_family_schedulable():
    """The whole point of the gate: an adapter existing is not a schedule."""
    for source_id in BUILD_ORDER:
        config = get_config(source_id)
        assert config.ensemble is not None
        assert config.ensemble.schedulable is False
        assert config.ingestible is False, (
            f"{source_id} became schedulable by being adapted"
        )


@pytest.mark.parametrize(
    "adapter",
    [
        ECCCREPSEnsembleAdapter(),
        ECMWFAIFSEnsembleAdapter(),
        ECMWFENSEnsembleAdapter(),
        NOAAGEFSEnsembleAdapter(),
    ],
)
def test_discovery_refuses_while_the_registry_says_the_family_is_not_schedulable(
    adapter,
):
    with pytest.raises(AdapterUnavailable) as error:
        adapter.discover(window_at())
    assert "not schedulable" in str(error.value)


# ------------------------------------------------------------------- 1. ECCC REPS


def test_reps_members_are_the_providers_own_two_digit_tokens():
    declaration = declaration_for("eccc-reps")
    members = member_identifiers(declaration)
    assert members[0] == "01" and members[-1] == "21"
    assert len(members) == declaration.member_count == 21


def test_reps_coverage_ids_name_one_coverage_per_member_per_field():
    assert coverage_id("REPS.MEM.ETA_NT.<member>", "01") == "REPS.MEM.ETA_NT.01"
    assert coverage_id("REPS.MEM.ETA_NT.<member>", "21") == "REPS.MEM.ETA_NT.21"
    keys = dict(stored_member_coverages("eccc-reps"))
    assert keys["total_cloud_opacity"] == "REPS.MEM.ETA_NT.<member>"
    # Wind direction is a declared gap: REPS publishes no components on any
    # member, so no coverage is formed for it.
    assert "wind_direction_10m" not in keys


def test_reps_requests_the_box_server_side_in_the_verified_shape():
    params = coverage_params("REPS.MEM.ETA_NT.01")
    assert ("REQUEST", "GetCoverage") in params
    assert ("FORMAT", "image/tiff") in params  # mandatory on this endpoint
    assert (
        "SCALESIZE",
        REPS_SCALESIZE,
    ) in params  # explicit server-resampled output shape
    assert ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326") in params
    subsets = [value for key, value in params if key == "SUBSET"]
    assert subsets == [
        f"long({REPS_EVIDENCE_BOX['west']},{REPS_EVIDENCE_BOX['east']})",
        f"lat({REPS_EVIDENCE_BOX['south']},{REPS_EVIDENCE_BOX['north']})",
    ]
    assert not any(key == "BBOX" for key, _ in params)  # WCS 2.0.1 takes SUBSET
    assert "COVERAGEID=REPS.MEM.ETA_NT.01" in coverage_url("REPS.MEM.ETA_NT.01")


def test_reps_declares_no_control_retrieval_while_no_control_is_identified():
    declaration = declaration_for("eccc-reps")
    assert declaration.control is not None  # the family publishes members
    assert (
        declaration.control.identifier is None
    )  # and none of them is named the control
    assert control_retrieval_for(declaration) is None


def reps_adapter(client: FakeClient) -> ECCCREPSEnsembleAdapter:
    def reader(payload: bytes, *, coverage: str, valid_time: datetime):
        key = next(
            key
            for key, template in stored_member_coverages("eccc-reps")
            if coverage.startswith(template.split("<")[0])
        )
        return member_field(UNITS_BY_KEY[key]).expand_dims(
            valid_time=[
                numpy.datetime64(valid_time.astimezone(UTC).replace(tzinfo=None), "ns")
            ]
        )

    return ECCCREPSEnsembleAdapter(client=client, reader=reader)


def test_reps_stores_every_published_member_field_and_flags_no_control(tmp_path: Path):
    client = FakeClient()
    result = reps_adapter(client).assemble(
        RunCandidate(
            provider_run_id="reps-2026090200", run_time=datetime(2026, 9, 2, tzinfo=UTC)
        ),
        window_at(),
        tmp_path,
    )

    provenance = result.artifacts[0].provenance
    assert provenance["storage_scope"]["applied"] == "every_published_field"
    # A subsetting family leaves nothing behind: wire and stored are one set.
    assert provenance["storage_scope"]["available_not_stored"] == []
    members = provenance["members"]
    assert len(members["present"]) == 21
    assert members["declared"] == 21
    assert members["control"] is None
    assert members["control_retrieval"] is None
    # One coverage request per member per stored field, all server side.
    assert len(client.urls) == 21 * len(stored_member_coverages("eccc-reps"))
    assert all("SCALESIZE" in url for url in client.urls)


def test_reps_publishes_one_member_axis_with_no_member_flagged_control(tmp_path: Path):
    client = FakeClient()
    adapter = reps_adapter(client)
    candidate = RunCandidate(
        provider_run_id="reps-2026090200", run_time=datetime(2026, 9, 2, tzinfo=UTC)
    )
    adapter.assemble(candidate, window_at(), tmp_path)

    stacked = reps_module.stack_members(
        {
            member: member_field("percent")
            for member in member_identifiers(declaration_for("eccc-reps"))
        },
        control=None,
    )
    assert stacked.sizes[MEMBER_DIM] == 21
    assert not bool(stacked[CONTROL_COORD].values.any())


def _coverage_tiff(
    *,
    keyed: bool = False,
    width: int = 133,
    height: int = 61,
    values: numpy.ndarray | None = None,
    nodata: object | None = None,
    tie: tuple[float, ...] = (0.0, 0.0, 0.0, -58.0, 50.5, 0.0),
    raster_type: int = 1,
    scale: tuple[float, ...] | None = None,
) -> bytes:
    image = Image.fromarray(
        numpy.full((height, width), 42.0, dtype=numpy.float32)
        if values is None
        else values,
        mode="F",
    )
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550] = scale or (12.0 / width, 5.5 / height, 0.0)
    tags[33922] = tie
    if keyed:
        tags[34735] = (1, 1, 0, 2, 1025, 0, 1, raster_type, 2048, 0, 1, 4326)
    if nodata is not None:
        tags[42113] = nodata
    output = io.BytesIO()
    image.save(output, format="TIFF", tiffinfo=tags)
    return output.getvalue()


def test_reps_real_reader_accepts_unkeyed_geomet_output_and_records_resampling():
    field = decode_reps_geotiff(
        _coverage_tiff(),
        coverage="REPS.MEM.ETA_NT.01",
        variable="total_cloud_opacity",
        valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
        bounds=REPS_EVIDENCE_BOX,
    )
    assert field.shape == (1, 61, 133)
    assert tuple(field.dims) == ("valid_time", "latitude", "longitude")
    assert field.attrs["crs_evidence"].endswith("no GeoKeyDirectoryTag")
    assert field.attrs["resampling"] == "server_resampled_method_unknown"
    assert (
        float(field.sel(latitude=47.5, longitude=-52.7, method="nearest").squeeze())
        == 42.0
    )


def test_reps_reader_masks_gdal_nodata_and_rejects_malformed_nodata():
    values = numpy.full((61, 133), 42.0, dtype=numpy.float32)
    values[3, 4] = -9999.0
    field = decode_reps_geotiff(
        _coverage_tiff(values=values, nodata="-9999"),
        coverage="REPS.MEM.ETA_NT.01",
        variable="total_cloud_opacity",
        valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
        bounds=REPS_EVIDENCE_BOX,
    )
    assert numpy.isnan(field.values[0, 3, 4])
    with pytest.raises(REPSCoverageError, match="malformed GDAL_NODATA"):
        decode_reps_geotiff(
            _coverage_tiff(nodata="missing"),
            coverage="REPS.MEM.ETA_NT.01",
            variable="total_cloud_opacity",
            valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
            bounds=REPS_EVIDENCE_BOX,
        )
    with pytest.raises(REPSCoverageError, match="non-finite GDAL_NODATA"):
        decode_reps_geotiff(
            _coverage_tiff(nodata="nan"),
            coverage="REPS.MEM.ETA_NT.01",
            variable="total_cloud_opacity",
            valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
            bounds=REPS_EVIDENCE_BOX,
        )


def test_reps_reader_honours_tiepoint_offsets_and_rejects_point_pixels():
    offset_tie = (2.0, 3.0, 0.0, -58.0 + 2 * 12.0 / 133, 50.5 - 3 * 5.5 / 61, 0.0)
    field = decode_reps_geotiff(
        _coverage_tiff(keyed=True, tie=offset_tie),
        coverage="REPS.MEM.ETA_NT.01",
        variable="total_cloud_opacity",
        valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
        bounds=REPS_EVIDENCE_BOX,
    )
    assert field.longitude.values[0] == pytest.approx(-58.0 + 0.5 * 12.0 / 133)
    assert field.latitude.values[0] == pytest.approx(50.5 - 0.5 * 5.5 / 61)
    with pytest.raises(Exception, match="RasterType"):
        decode_reps_geotiff(
            _coverage_tiff(keyed=True, raster_type=2),
            coverage="REPS.MEM.ETA_NT.01",
            variable="total_cloud_opacity",
            valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
            bounds=REPS_EVIDENCE_BOX,
        )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"scale": (float("nan"), 5.5 / 61, 0.0)}, "scale/tie-point"),
        ({"tie": (0.0, 0.0, 0.0, -58.0, float("inf"), 0.0)}, "scale/tie-point"),
        ({"width": 132}, "shape"),
    ],
)
def test_reps_reader_rejects_nonfinite_transform_and_wrong_shape(kwargs, message):
    with pytest.raises(REPSCoverageError, match=message):
        decode_reps_geotiff(
            _coverage_tiff(**kwargs),
            coverage="REPS.MEM.ETA_NT.01",
            variable="total_cloud_opacity",
            valid_time=datetime(2026, 9, 5, 18, tzinfo=UTC),
            bounds=REPS_EVIDENCE_BOX,
        )


def test_reps_pressure_level_is_never_formed_when_not_advertised():
    template = "REPS.MEM.PRES_HR.<hPa>.<member>"
    advertised = ("REPS.MEM.PRES_HR.700.01",)
    assert (
        pressure_coverage_id(
            template, level_hpa=700, member="01", advertised=advertised
        )
        == advertised[0]
    )
    with pytest.raises(Exception, match="not advertised"):
        pressure_coverage_id(
            template, level_hpa=775, member="01", advertised=advertised
        )


def test_one_missing_reps_member_makes_the_selected_family_partial(tmp_path: Path):
    client = FakeClient(missing=("ETA_NT.07",))
    result = reps_adapter(client).assemble(
        RunCandidate(
            "reps-partial",
            datetime(2026, 9, 5, 12, tzinfo=UTC),
            detail={"valid_time": datetime(2026, 9, 5, 18, tzinfo=UTC)},
        ),
        window_at(datetime(2026, 9, 5, 18, tzinfo=UTC)),
        tmp_path,
        selected_keys=("total_cloud_opacity", "wind_speed_10m"),
    )
    assert result.complete is False
    assert (
        "decode_error:coverage:REPS.MEM.ETA_NT.07"
        in result.artifacts[0].provenance["quality"]["flags"]
    )


def test_reps_selected_subset_never_claims_whole_family_completion(tmp_path: Path):
    result = reps_adapter(FakeClient()).assemble(
        RunCandidate(
            "reps-subset",
            datetime(2026, 9, 5, 12, tzinfo=UTC),
            detail={"valid_time": datetime(2026, 9, 5, 18, tzinfo=UTC)},
        ),
        window_at(datetime(2026, 9, 5, 18, tzinfo=UTC)),
        tmp_path,
        selected_keys=("total_cloud_opacity", "wind_speed_10m"),
    )
    accounting = result.artifacts[0].provenance["field_accounting"]
    assert accounting["advertised_coverages"] == 1239
    assert accounting["catalogued_surface_fields"] == 7
    assert len(accounting["deferred_surface_fields"]) == 5
    assert accounting["other_advertised_coverages_deferred"] == 1092
    assert accounting["whole_family_complete"] is False
    assert result.complete is False


def test_reps_wrong_or_missing_valid_time_fails_closed(tmp_path: Path):
    def wrong_time_reader(payload: bytes, *, coverage: str, valid_time: datetime):
        return member_field("percent").expand_dims(
            valid_time=[numpy.datetime64("2026-09-05T15:00:00", "ns")]
        )

    adapter = ECCCREPSEnsembleAdapter(client=FakeClient(), reader=wrong_time_reader)
    result = adapter.assemble(
        RunCandidate(
            "reps-wrong-time",
            datetime(2026, 9, 5, 12, tzinfo=UTC),
            detail={"valid_time": datetime(2026, 9, 5, 18, tzinfo=UTC)},
        ),
        window_at(datetime(2026, 9, 5, 18, tzinfo=UTC)),
        tmp_path,
        selected_keys=("total_cloud_opacity",),
    )
    assert result.complete is False
    assert any(
        "valid_time" in flag
        for flag in result.artifacts[0].provenance["quality"]["flags"]
    )

    class MissingTimeAdapter(ECCCREPSEnsembleAdapter):
        pass

    with pytest.raises(
        AdapterUnavailable, match="offset-aware run_time and valid_time"
    ):
        MissingTimeAdapter(client=FakeClient()).assemble(
            RunCandidate("reps-no-time", None),
            window_at(),
            tmp_path,
            selected_keys=("total_cloud_opacity",),
        )


def test_reps_naive_or_blank_run_identity_is_refused_before_http(tmp_path: Path):
    client = FakeClient()
    adapter = reps_adapter(client)
    with pytest.raises(AdapterUnavailable, match="provider_run_id"):
        adapter.assemble(
            RunCandidate(
                "",
                datetime(2026, 9, 5, 12),  # noqa: DTZ001 - intentional rejection
                detail={"valid_time": datetime(2026, 9, 5, 18)},  # noqa: DTZ001
            ),
            window_at(),
            tmp_path,
            selected_keys=("total_cloud_opacity",),
        )
    assert client.urls == []


def test_reps_request_and_artifact_preserve_exact_run_and_valid_identity(
    tmp_path: Path,
):
    client = FakeClient()
    result = reps_adapter(client).assemble(
        RunCandidate(
            "reps-exact",
            datetime(2026, 9, 5, 12, tzinfo=UTC),
            detail={"valid_time": datetime(2026, 9, 5, 18, tzinfo=UTC)},
        ),
        window_at(datetime(2026, 9, 5, 18, tzinfo=UTC)),
        tmp_path,
        selected_keys=("total_cloud_opacity",),
    )
    assert all("TIME=2026-09-05T18%3A00%3A00Z" in url for url in client.urls)
    assert all(
        "DIM_REFERENCE_TIME=2026-09-05T12%3A00%3A00Z" in url for url in client.urls
    )
    provenance = result.artifacts[0].provenance
    assert provenance["provider_run_id"] == "reps-exact"
    assert provenance["valid_times"] == ["2026-09-05T18:00:00+00:00"]
    assert len(_declared_valid_time_nanoseconds(provenance)) == 1


class GEPSFixtureClient:
    def __init__(self, *, missing: str | None = None):
        self.missing = missing

    def get(self, url: str):
        if self.missing and self.missing in url:
            return FakeResponse(b"<ExceptionReport>NoMatch</ExceptionReport>")
        return FakeResponse(_coverage_tiff(keyed=True, width=24, height=11))

    def get_bytes(self, url: str, *, max_bytes: int):
        response = self.get(url)
        assert len(response.content) <= max_bytes
        return response.content, response.headers


def test_geps_retains_provider_reductions_without_a_member_axis(tmp_path: Path):
    artifact = fetch_geps_reductions(
        valid_time=datetime(2026, 9, 5, 12, tzinfo=UTC),
        reference_time=datetime(2026, 9, 5, 0, tzinfo=UTC),
        workdir=tmp_path,
        client=GEPSFixtureClient(),
    )
    dataset = open_artifact(artifact.payload_path)
    assert set(dataset.data_vars) == {item.variable for item in SELECTED_REDUCTIONS}
    assert MEMBER_DIM not in dataset.dims
    assert artifact.provenance["members_published"] is False
    assert artifact.provenance["computed_here"] is False
    assert artifact.provenance["provider_run_id"] == "geps-20260905T00Z-f012"
    assert artifact.provenance["valid_times"] == ["2026-09-05T12:00:00+00:00"]
    assert len(_declared_valid_time_nanoseconds(artifact.provenance)) == 1
    assert artifact.provenance["field_accounting"] == {
        "advertised_coverages": 532,
        "selected_reductions": 5,
        "other_advertised_coverages_deferred": 527,
        "whole_family_complete": False,
    }
    assert {row["provider_statistic"] for row in artifact.provenance["reductions"]} == {
        "mean",
        "standard_deviation",
        "percentile",
        "threshold_probability",
    }


def test_missing_selected_geps_reduction_fails_without_an_artifact(tmp_path: Path):
    with pytest.raises(Exception, match="not a TIFF"):
        fetch_geps_reductions(
            valid_time=datetime(2026, 9, 5, 12, tzinfo=UTC),
            reference_time=datetime(2026, 9, 5, 0, tzinfo=UTC),
            workdir=tmp_path,
            client=GEPSFixtureClient(missing="ERSSTD"),
        )
    assert not (tmp_path / "eccc_geps_reductions.zarr.zip").exists()


RECEIPT_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/eccc_ensemble/eccc-ensemble-2026-09-05.receipt.json"
)


def test_live_capture_receipt_matches_the_request_shape_the_adapter_forms():
    """The retained evidence is a receipt, not a payload.

    Provider payloads were removed from history per the owner decision of
    2026-09-05 (issue 70). What stays is request identity, byte counts,
    checksums and times, and it has to agree with what the adapter actually
    asks GeoMet for.
    """
    receipt = json.loads(RECEIPT_PATH.read_text())
    shape = receipt["request_shape"]
    assert shape["SCALESIZE"] == REPS_SCALESIZE
    assert shape["SUBSET"] == [
        f"long({REPS_EVIDENCE_BOX['west']},{REPS_EVIDENCE_BOX['east']})",
        f"lat({REPS_EVIDENCE_BOX['south']},{REPS_EVIDENCE_BOX['north']})",
    ]
    params = dict(coverage_params("REPS.MEM.ETA_NT.01"))
    assert params["SUBSETTINGCRS"] == shape["SUBSETTINGCRS"]
    assert params["FORMAT"] == shape["FORMAT"]

    rows = receipt["representative_responses"]
    assert {row["coverage_id"] for row in rows if row["kind"] == "geps"} == {
        item.coverage_id for item in SELECTED_REDUCTIONS
    }
    for row in rows:
        assert set(row) == {
            "kind",
            "coverage_id",
            "source_uri",
            "decoded_body_bytes",
            "sha256",
            "retrieved_at",
            "content_type",
        }  # identity and integrity only; no decoded values
        assert len(row["sha256"]) == 64
        assert row["decoded_body_bytes"] > 0
    assert receipt["totals"]["requests"] == 48
    assert receipt["field_accounting"]["reps"]["advertised_coverages"] == 1239
    for entry in receipt["rebuilt_artifacts"].values():
        assert entry["retained_in_git"] is False


def test_reps_member_artifact_round_trips_through_reader_without_default_point_fallback(
    monkeypatch, tmp_path: Path
):
    # The artifact is built here from the synthetic member fixtures, in the
    # same 21-member shape the live capture produced. No provider payload is
    # stored in Git (owner decision of 2026-09-05, issue 70); the live capture
    # is evidenced by the receipt table in the change proposal and by
    # ``fixtures/eccc_ensemble/eccc-ensemble-2026-09-05.receipt.json``.
    built = reps_adapter(FakeClient()).assemble(
        RunCandidate(
            "reps-20260905T12Z-f006",
            datetime(2026, 9, 5, 12, tzinfo=UTC),
            detail={"valid_time": datetime(2026, 9, 5, 18, tzinfo=UTC)},
        ),
        window_at(datetime(2026, 9, 5, 18, tzinfo=UTC)),
        tmp_path,
        selected_keys=("total_cloud_opacity", "wind_speed_10m"),
    )
    artifact_path = built.artifacts[0].payload_path
    dataset = open_artifact(artifact_path)
    current = CurrentArtifact(
        source_id="eccc-reps",
        logical_name="members",
        revision_id="retained-reps-20260905",
        object_key=str(artifact_path),
        media_type="application/zarr+zip",
        byte_size=artifact_path.stat().st_size,
        provenance={
            "members": {
                "declared": 21,
                "present": list(member_identifiers(declaration_for("eccc-reps"))),
                "missing": [],
                "control": None,
            }
        },
        published_at=datetime(2026, 9, 5, 18, tzinfo=UTC),
        run_time=datetime(2026, 9, 5, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 5, 18, tzinfo=UTC),
        provider_run_id="reps-20260905T12Z-f006",
        native_crs="EPSG:4326",
    )

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)

        def current(self):
            return [current]

        def open(self, _artifact):
            return dataset

        def assert_object_store_reachable(self):
            pass

    manifest = SimpleNamespace(
        class_for=lambda _name: "retrieved", evidence_classes=("retrieved",)
    )
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)
    monkeypatch.setitem(api_store.FIELD_BY_VARIABLE, "wind_speed_10m", "wind_speed_10m")
    harness = Harness()
    samples = harness.sample_point(
        47.56, -52.71, datetime(2026, 9, 5, 18, tzinfo=UTC), member="01"
    )
    assert {sample.variable for sample in samples} == {
        "total_cloud_opacity",
        "wind_speed_10m",
    }
    assert all(sample.value is not None for sample in samples)
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_module, "now", lambda: datetime(2026, 9, 5, 18, tzinfo=UTC))
    response = TestClient(app).get(
        "/api/experiments/weather/v0/point",
        params={
            "latitude": 47.56,
            "longitude": -52.71,
            "valid_time": "2026-09-05T18:00:00Z",
            "member": "01",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["operational"] is False
    assert all(item["provenance"]["source_id"] != "eccc-reps" for item in body["fields"])


# ------------------------------------------------------------------ 2. AIFS-ENS

AIFS_PF_INDEX = "\n".join(
    json.dumps(
        {
            "domain": "g",
            "date": "20260901",
            "time": "0000",
            "type": "pf",
            "number": str(number),
            "param": param,
            "step": "24",
            "_offset": (number * 10 + index) * 1_000_000,
            "_length": 1_400_000,
        }
    )
    for number in (1, 2, 3)
    for index, param in enumerate(("tcc", "2t", "z"))
)

AIFS_CF_INDEX = "\n".join(
    json.dumps(
        {
            "domain": "g",
            "date": "20260901",
            "time": "0000",
            "type": "cf",
            "param": param,
            "step": "24",
            "_offset": index * 1_000_000,
            "_length": 1_400_000,
        }
    )
    for index, param in enumerate(("tcc", "2t", "z"))
)

AIFS_PF_URL = "https://data.ecmwf.int/forecasts/20260901/00z/aifs-ens/0p25/enfo/20260901000000-24h-enfo-pf.grib2"
AIFS_CF_URL = AIFS_PF_URL.replace("-pf.", "-cf.")


def index_url(url: str) -> str:
    return f"{url.removesuffix('.grib2')}.index"


def ecmwf_reader(path, *, param: str, member: str, bounds):
    key = {"tcc": "total_cloud_geometric", "2t": "temperature_2m"}[param]
    return member_field(UNITS_BY_KEY[key])


def test_aifs_ens_reads_the_grib_number_and_the_separate_control_file():
    by_member, published = select_member_ranges(
        AIFS_PF_INDEX, family_upstream_params("ecmwf-aifs-ens"), control_identifier="0"
    )
    assert sorted(by_member) == ["1", "2", "3"]  # the pf file carries no control
    assert "z" in published  # published, outside the family fields, not fetched
    assert "z" not in by_member["1"]

    control_ranges, _ = select_member_ranges(
        AIFS_CF_INDEX, family_upstream_params("ecmwf-aifs-ens"), control_identifier="0"
    )
    # The cf record takes the registry's control identifier, not its own number.
    assert list(control_ranges) == ["0"]


def test_the_index_parser_keeps_the_member_fields_the_range_parser_drops():
    records = parse_ecmwf_index_records(AIFS_PF_INDEX)
    assert {record.number for record in records} == {"1", "2", "3"}
    assert {record.record_type for record in records} == {"pf"}


def aifs_adapter(client: FakeClient) -> ECMWFAIFSEnsembleAdapter:
    return ECMWFAIFSEnsembleAdapter(client=client, reader=ecmwf_reader)


def test_aifs_ens_assembles_two_files_into_one_member_axis(tmp_path: Path):
    client = FakeClient(
        texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX, index_url(AIFS_CF_URL): AIFS_CF_INDEX}
    )
    result = aifs_adapter(client).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-2026090100",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )

    members = result.artifacts[0].provenance["members"]
    assert members["declared"] == 51  # the registry's count, control included
    assert sorted(members["present"]) == ["0", "1", "2", "3"]
    assert members["control"] == "0"
    assert members["control_retrieval"] == "separate_file"
    # One axis, one artifact: the control is never a second artifact.
    assert len(result.artifacts) == 1
    assert result.artifacts[0].provenance["control_file"] == AIFS_CF_URL


def test_aifs_ens_publishes_partial_with_the_control_named_when_cf_is_missing(tmp_path: Path):
    client = FakeClient(texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX}, missing=("-cf.",))
    result = aifs_adapter(client).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-2026090100",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )

    members = result.artifacts[0].provenance["members"]
    assert "0" in members["missing"]  # the control is named as the missing member
    assert "0" not in members["present"]
    assert result.complete is False  # partial, not a complete run of the perturbed set
    flags = result.artifacts[0].provenance["quality"]["flags"]
    assert any(flag.startswith("control_missing:0") for flag in flags)
    # The perturbed members that did arrive still publish.
    assert result.artifacts


def test_aifs_ens_stores_only_the_catalogue_family_fields(tmp_path: Path):
    client = FakeClient(
        texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX, index_url(AIFS_CF_URL): AIFS_CF_INDEX}
    )
    result = aifs_adapter(client).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-2026090100",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )
    scope = result.artifacts[0].provenance["storage_scope"]
    assert scope["applied"] == "family_fields_only"
    assert "z" in scope["available_not_stored"]  # published, deliberately not stored


# ------------------------------------------------------------------- 3. IFS ENS

IFS_EF_URL = "https://data.ecmwf.int/forecasts/20260901/00z/ifs/0p25/enfo/20260901000000-24h-enfo-ef.grib2"

#: The file as it was actually measured on 2026-09-02: type=pf numbers only, and
#: no cf record anywhere in it. That measurement is the reason the control's
#: location is declared unverified.
IFS_EF_INDEX = "\n".join(
    json.dumps(
        {
            "domain": "g",
            "date": "20260901",
            "time": "0000",
            "type": "pf",
            "number": str(number),
            "param": param,
            "step": "24",
            "_offset": (number * 10 + index) * 600_000,
            "_length": 570_000,
        }
    )
    for number in (1, 2)
    for index, param in enumerate(("tcc", "2t", "gh"))
)


def test_ifs_ens_reports_the_control_missing_rather_than_failing_the_run(tmp_path: Path):
    client = FakeClient(texts={index_url(IFS_EF_URL): IFS_EF_INDEX})
    adapter = ECMWFENSEnsembleAdapter(client=client, reader=ecmwf_reader)

    # No cf-typed record exists in the file, which is what was measured. The run
    # must publish partial, not raise: the control's location is unverified, and
    # the 50 perturbed members that arrive are real.
    result = adapter.assemble(
        RunCandidate(
            provider_run_id="ifs-ens-2026090100",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": IFS_EF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )

    members = result.artifacts[0].provenance["members"]
    assert members["control"] == "0"
    assert "0" in members["missing"]
    assert members["control_retrieval"] is None
    assert result.complete is False
    assert result.artifacts  # published partial, not refused


def test_ifs_ens_leaves_control_retrieval_unstated_when_open_enfo_exposes_none():
    adapter = ECMWFENSEnsembleAdapter()
    assert adapter.control_retrieval() is None
    assert adapter.declared_members()[0] == "0"
    assert len(adapter.declared_members()) == 51


IFS_OPER_URL = "https://data.ecmwf.int/forecasts/20260901/00z/ifs/0p25/oper/20260901000000-24h-oper-fc.grib2"


def ifs_control_index(*, stream="oper", record_type="fc", number=None, date="20260901", param_override=None):
    return "\n".join(
        json.dumps(
            {
                "domain": "g", "date": date, "time": "0000", "type": record_type,
                "stream": stream, "number": number, "param": param_override or param,
                "step": "24", "_offset": index * 600_000, "_length": 570_000,
            }
        )
        for index, param in enumerate(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"])
    )


def mapped_control_reader(path, *, param: str, member: str, bounds):
    field = ecmwf_reader(path, param=param, member=member, bounds=bounds)
    field.attrs.update({
        "GRIB_dataDate": 20260901, "GRIB_dataTime": 0, "GRIB_stepRange": "24",
        "GRIB_shortName": param, "GRIB_dataType": "fc", "GRIB_marsStream": "oper",
        "GRIB_validityDate": 20260902, "GRIB_validityTime": 0,
    })
    return field


def ifs_mapped_candidate(mapping=None, url=IFS_OPER_URL):
    return RunCandidate(
        provider_run_id="ifs-ens-20260901000000-f024",
        run_time=datetime(2026, 9, 1, tzinfo=UTC),
        detail={
            "member_url": IFS_EF_URL,
            "control_url": url,
            "lead_hours": 24,
            "ifs_cycle_50r1_control_mapping": mapping if mapping is not None else {
                **IFS_CYCLE_50R1_CONTROL_MAPPING,
                "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
            },
        },
    )


def test_ifs_cycle_50r1_maps_only_explicit_oper_fc_fields_to_control_zero(tmp_path: Path):
    client = FakeClient(texts={
        index_url(IFS_EF_URL): IFS_EF_INDEX,
        index_url(IFS_OPER_URL): ifs_control_index(),
    })
    result = ECMWFENSEnsembleAdapter(client=client, reader=mapped_control_reader).assemble(
        ifs_mapped_candidate(), window_at(), tmp_path
    )
    provenance = result.artifacts[0].provenance
    assert provenance["members"]["control"] == "0"
    assert "0" in provenance["members"]["present"]
    assert provenance["members"]["control_retrieval"] == "separate_file"
    assert provenance["mapped_control"]["source_stream"] == "oper"
    assert provenance["mapped_control"]["source_type"] == "fc"
    assert provenance["mapped_control"]["source_url"] == IFS_OPER_URL
    assert provenance["provider_run_id"] == "ifs-ens-20260901000000-f024"
    assert provenance["valid_times"] == ["2026-09-02T00:00:00+00:00"]


@pytest.mark.parametrize(
    ("index_text", "mapping", "url", "flag"),
    [
        (ifs_control_index(stream="enfo"), None, IFS_OPER_URL, "mapped_control_index_identity"),
        (ifs_control_index(record_type="pf"), None, IFS_OPER_URL, "mapped_control_index_identity"),
        (ifs_control_index(number="1"), None, IFS_OPER_URL, "mapped_control_index_identity"),
        (ifs_control_index(), {"producer": "ECMWF"}, IFS_OPER_URL, "mapped_control_authorization_identity"),
        (ifs_control_index(), None, IFS_OPER_URL.replace("/oper/", "/enfo/"), "mapped_control_url_identity"),
    ],
)
def test_ifs_control_mapping_rejects_wrong_source_member_or_authorization(
    tmp_path: Path, index_text, mapping, url, flag
):
    texts = {index_url(IFS_EF_URL): IFS_EF_INDEX, index_url(url): index_text}
    result = ECMWFENSEnsembleAdapter(client=FakeClient(texts=texts), reader=mapped_control_reader).assemble(
        ifs_mapped_candidate(mapping=mapping, url=url), window_at(), tmp_path
    )
    assert result.complete is False
    assert "0" in result.artifacts[0].provenance["members"]["missing"]
    assert any(flag in item for item in result.artifacts[0].provenance["quality"]["flags"])


def test_ifs_control_mapping_rejects_payload_field_and_run_identity(tmp_path: Path):
    def wrong_payload(path, *, param: str, member: str, bounds):
        field = mapped_control_reader(path, param=param, member=member, bounds=bounds)
        if param == "tcc":
            field.attrs["GRIB_shortName"] = "2t"
        return field

    client = FakeClient(texts={index_url(IFS_EF_URL): IFS_EF_INDEX, index_url(IFS_OPER_URL): ifs_control_index()})
    result = ECMWFENSEnsembleAdapter(client=client, reader=wrong_payload).assemble(
        ifs_mapped_candidate(), window_at(), tmp_path
    )
    assert result.complete is False
    assert any("member:oper-fc-control0:0:tcc" in item for item in result.artifacts[0].provenance["quality"]["flags"])


def test_ifs_control_mapping_rejects_payload_stream_identity(tmp_path: Path):
    def wrong_stream(path, *, param: str, member: str, bounds):
        field = mapped_control_reader(path, param=param, member=member, bounds=bounds)
        field.attrs["GRIB_marsStream"] = "wave"
        return field

    client = FakeClient(texts={index_url(IFS_EF_URL): IFS_EF_INDEX, index_url(IFS_OPER_URL): ifs_control_index()})
    result = ECMWFENSEnsembleAdapter(client=client, reader=wrong_stream).assemble(
        ifs_mapped_candidate(), window_at(), tmp_path
    )
    assert result.complete is False
    assert "0" in result.artifacts[0].provenance["members"]["missing"]


def test_experiment_discovery_enumerates_the_full_window_cadence_without_scheduling():
    base = "https://data.ecmwf.int/forecasts"
    directory = f"{base}/20260901/00z/aifs-ens/0p25/enfo/"
    files = "\n".join(
        f'<a href="/forecasts/20260901/00z/aifs-ens/0p25/enfo/20260901000000-{lead}h-enfo-{suffix}.grib2">x</a>'
        for lead in (0, 6, 12, 18, 24, 30)
        for suffix in ("pf", "cf")
    )
    client = FakeClient(
        texts={
            f"{base}/": '<a href="/forecasts/20260901/">date</a>',
            f"{base}/20260901/": '<a href="/forecasts/20260901/00z/">cycle</a>',
            directory: files,
        }
    )
    adapter = aifs_adapter(client)
    window = FetchWindow(
        now=datetime(2026, 9, 1, 12, tzinfo=UTC), back_hours=12, forward_hours=12
    )

    candidates = adapter.discover_experiment(window)

    assert sorted(item.detail["lead_hours"] for item in candidates) == [0, 6, 12, 18, 24]
    assert all(item.detail["control_url"].endswith("-cf.grib2") for item in candidates)
    assert len(client.urls) == 3  # root, date and one full-cycle product listing
    with pytest.raises(AdapterUnavailable, match="not schedulable"):
        adapter.discover(window)


def test_ifs_discovery_maps_only_an_exact_advertised_oper_fc_control():
    base = "https://data.ecmwf.int/forecasts"
    enfo = f"{base}/20260901/00z/ifs/0p25/enfo/"
    oper = f"{base}/20260901/00z/ifs/0p25/oper/"
    ef_name = "20260901000000-24h-enfo-ef.grib2"
    fc_name = "20260901000000-24h-oper-fc.grib2"
    client = FakeClient(texts={
        f"{base}/": '<a href="/forecasts/20260901/">date</a>',
        f"{base}/20260901/": '<a href="/forecasts/20260901/00z/">cycle</a>',
        enfo: f'<a href="{ef_name}">ef</a>',
        oper: f'<a href="{fc_name}">fc</a><a href="20260901000000-30h-oper-fc.grib2">other</a>',
    })
    adapter = ECMWFENSEnsembleAdapter(client=client)
    candidates = adapter.discover_experiment(
        FetchWindow(datetime(2026, 9, 2, tzinfo=UTC), back_hours=0, forward_hours=0),
        include_ifs_cycle_50r1_control=True,
    )
    assert len(candidates) == 1
    assert candidates[0].detail["control_url"] == oper + fc_name
    assert candidates[0].detail["ifs_cycle_50r1_control_mapping"]["fields"] == list(
        IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]
    )


def test_ifs_discovery_does_not_infer_a_control_when_exact_lead_is_absent():
    base = "https://data.ecmwf.int/forecasts"
    enfo = f"{base}/20260901/00z/ifs/0p25/enfo/"
    oper = f"{base}/20260901/00z/ifs/0p25/oper/"
    client = FakeClient(texts={
        f"{base}/": '<a href="/forecasts/20260901/">date</a>',
        f"{base}/20260901/": '<a href="/forecasts/20260901/00z/">cycle</a>',
        enfo: '<a href="20260901000000-24h-enfo-ef.grib2">ef</a>',
        oper: '<a href="20260901000000-30h-oper-fc.grib2">different lead</a>',
    })
    candidate = adapter = ECMWFENSEnsembleAdapter(client=client).discover_experiment(
        FetchWindow(datetime(2026, 9, 2, tzinfo=UTC), back_hours=0, forward_hours=0),
        include_ifs_cycle_50r1_control=True,
    )[0]
    assert "control_url" not in candidate.detail
    assert "ifs_cycle_50r1_control_mapping" not in candidate.detail


def test_ifs_discovery_keeps_perturbed_candidate_when_oper_listing_is_unavailable():
    base = "https://data.ecmwf.int/forecasts"
    enfo = f"{base}/20260901/00z/ifs/0p25/enfo/"
    client = FakeClient(
        texts={
            f"{base}/": '<a href="/forecasts/20260901/">date</a>',
            f"{base}/20260901/": '<a href="/forecasts/20260901/00z/">cycle</a>',
            enfo: '<a href="20260901000000-24h-enfo-ef.grib2">ef</a>',
        },
        missing=("/oper/",),
    )
    candidates = ECMWFENSEnsembleAdapter(client=client).discover_experiment(
        FetchWindow(datetime(2026, 9, 2, tzinfo=UTC), back_hours=0, forward_hours=0),
        include_ifs_cycle_50r1_control=True,
    )
    assert len(candidates) == 1
    assert "control_url" not in candidates[0].detail


def test_ifs_mapped_control_discovery_has_a_finite_21_request_ceiling():
    base = "https://data.ecmwf.int/forecasts"
    dates = ("20260901", "20260902", "20260903", "20260904")
    texts = {f"{base}/": "".join(f'<a href="/forecasts/{date}/">d</a>' for date in dates)}
    for date in dates:
        texts[f"{base}/{date}/"] = (
            f'<a href="/forecasts/{date}/00z/">00</a>'
            f'<a href="/forecasts/{date}/12z/">12</a>'
        )
        for cycle in ("00", "12"):
            texts[f"{base}/{date}/{cycle}z/ifs/0p25/enfo/"] = ""
            texts[f"{base}/{date}/{cycle}z/ifs/0p25/oper/"] = ""
    client = FakeClient(texts=texts)
    ECMWFENSEnsembleAdapter(client=client).discover_experiment(
        FetchWindow(datetime(2026, 9, 3, tzinfo=UTC), back_hours=96, forward_hours=96),
        include_ifs_cycle_50r1_control=True,
    )
    assert len(client.urls) == MAX_MAPPED_CONTROL_DISCOVERY_REQUESTS == 21


def test_ecmwf_index_run_identity_mismatch_fails_closed(tmp_path: Path):
    bad_index = AIFS_PF_INDEX.replace('"date": "20260901"', '"date": "20260902"')
    client = FakeClient(texts={index_url(AIFS_PF_URL): bad_index}, missing=("-cf.",))
    with pytest.raises(AdapterUnavailable, match="no member decoded"):
        aifs_adapter(client).assemble(
            RunCandidate(
                provider_run_id="aifs-ens-20260901000000-f024",
                run_time=datetime(2026, 9, 1, tzinfo=UTC),
                detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
            ),
            window_at(),
            tmp_path,
        )


def test_ecmwf_missing_selected_field_is_incomplete(tmp_path: Path):
    without_cloud = "\n".join(
        line for line in AIFS_PF_INDEX.splitlines() if json.loads(line)["param"] != "tcc"
    )
    client = FakeClient(texts={index_url(AIFS_PF_URL): without_cloud}, missing=("-cf.",))
    result = aifs_adapter(client).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-20260901000000-f024",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )
    assert result.complete is False
    assert any("total_cloud_geometric" in flag for flag in result.artifacts[0].provenance["quality"]["flags"])


def test_ecmwf_wrong_normalized_units_fail_qc(tmp_path: Path):
    def wrong_units(path, *, param: str, member: str, bounds):
        field = ecmwf_reader(path, param=param, member=member, bounds=bounds)
        if param == "tcc":
            field.attrs["units"] = "fraction"
        return field

    client = FakeClient(
        texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX, index_url(AIFS_CF_URL): AIFS_CF_INDEX}
    )
    result = ECMWFAIFSEnsembleAdapter(client=client, reader=wrong_units).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-20260901000000-f024",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )
    assert result.qc_passed is False
    assert any("bad_units" in flag for flag in result.artifacts[0].provenance["quality"]["flags"])


def test_ecmwf_grid_identity_difference_fails_instead_of_aligning_with_nulls(tmp_path: Path):
    def mismatched_reader(path, *, param: str, member: str, bounds):
        field = ecmwf_reader(path, param=param, member=member, bounds=bounds)
        if member == "2":
            field = field.assign_coords(longitude=[-53.0, -52.0, -50.75])
        return field

    client = FakeClient(
        texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX, index_url(AIFS_CF_URL): AIFS_CF_INDEX}
    )
    with pytest.raises(AdapterUnavailable, match="grid_identity:2"):
        ECMWFAIFSEnsembleAdapter(client=client, reader=mismatched_reader).assemble(
            RunCandidate(
                provider_run_id="aifs-ens-20260901000000-f024",
                run_time=datetime(2026, 9, 1, tzinfo=UTC),
                detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
            ),
            window_at(),
            tmp_path,
        )


def test_ecmwf_artifact_records_exact_valid_time_ranges_bytes_and_checksums(tmp_path: Path):
    client = FakeClient(
        texts={index_url(AIFS_PF_URL): AIFS_PF_INDEX, index_url(AIFS_CF_URL): AIFS_CF_INDEX}
    )
    result = aifs_adapter(client).assemble(
        RunCandidate(
            provider_run_id="aifs-ens-20260901000000-f024",
            run_time=datetime(2026, 9, 1, tzinfo=UTC),
            detail={"member_url": AIFS_PF_URL, "lead_hours": 24},
        ),
        window_at(),
        tmp_path,
    )
    artifact = result.artifacts[0]
    dataset = open_artifact(artifact.payload_path)
    assert str(dataset.valid_time.values[0]).startswith("2026-09-02T00:00:00")
    evidence = artifact.provenance["upstream_ranges"]
    assert evidence
    assert artifact.provenance["upstream_bytes"] == sum(item["byte_size"] for item in evidence)
    assert all(len(item["sha256"]) == 64 for item in evidence)


class ExactRangeResponse:
    def __init__(
        self, status: int, payload: bytes, content_range: str, *, content_length: str = ""
    ) -> None:
        self.status_code = status
        self.headers = {"Content-Range": content_range}
        if content_length:
            self.headers["Content-Length"] = content_length
        self.payload = payload
        self.chunks_read = 0

    def iter_bytes(self):
        for offset in range(0, len(self.payload), 2):
            self.chunks_read += 1
            yield self.payload[offset : offset + 2]

    def close(self) -> None:
        pass


def exact_range_client(response: ExactRangeResponse):
    client = object.__new__(__import__("ingest.http", fromlist=["PoliteClient"]).PoliteClient)
    def request(*_args, **kwargs):
        assert kwargs["stream"] is True
        return response

    client._request = request
    return client


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (ExactRangeResponse(200, b"whole", ""), "range_status"),
        (ExactRangeResponse(206, b"12345", "bytes 0-5/100"), "range_length"),
        (ExactRangeResponse(206, b"123456", "bytes 1-6/100"), "range_content_range"),
        (ExactRangeResponse(206, b"123456", "bytes 0-5/*"), "range_content_range"),
    ],
)
def test_ecmwf_exact_range_refuses_full_body_short_body_and_wrong_identity(
    tmp_path: Path, response: ExactRangeResponse, reason: str
):
    destination = tmp_path / "x"
    with pytest.raises(ValueError, match=reason):
        _download_verified_range(
            exact_range_client(response), "https://example.test/run", destination, (0, 5)
        )
    assert not destination.exists()
    if reason in {"range_status", "range_content_range"}:
        assert response.chunks_read == 0


def test_ecmwf_exact_range_stops_reading_when_stream_exceeds_index_length(tmp_path: Path):
    response = ExactRangeResponse(206, b"1234567890", "bytes 0-5/100")
    destination = tmp_path / "x"

    with pytest.raises(ValueError, match="range_length:8: expected 6"):
        _download_verified_range(
            exact_range_client(response), "https://example.test/run", destination, (0, 5)
        )

    assert response.chunks_read == 4
    assert not destination.exists()


def test_ecmwf_exact_range_records_verified_response_identity(tmp_path: Path):
    response = ExactRangeResponse(206, b"123456", "bytes 0-5/100", content_length="6")
    evidence: dict[str, object] = {}

    size = _download_verified_range(
        exact_range_client(response),
        "https://example.test/run",
        tmp_path / "x",
        (0, 5),
        response_evidence=evidence,
    )

    assert size == 6
    assert evidence == {"http_status": 206, "content_range": "bytes 0-5/100"}
    assert (tmp_path / "x").read_bytes() == b"123456"


def test_ecmwf_exact_range_refuses_wrong_declared_length_without_reading(tmp_path: Path):
    response = ExactRangeResponse(
        206, b"123456", "bytes 0-5/100", content_length="999999999"
    )

    with pytest.raises(ValueError, match="range_length:999999999: expected 6"):
        _download_verified_range(
            exact_range_client(response), "https://example.test/run", tmp_path / "x", (0, 5)
        )

    assert response.chunks_read == 0
    assert not (tmp_path / "x").exists()


def test_ecmwf_exact_range_refuses_malformed_declared_length_without_reading(tmp_path: Path):
    response = ExactRangeResponse(
        206, b"123456", "bytes 0-5/100", content_length="six"
    )

    with pytest.raises(ValueError, match="range_length:six: expected 6"):
        _download_verified_range(
            exact_range_client(response), "https://example.test/run", tmp_path / "x", (0, 5)
        )

    assert response.chunks_read == 0
    assert not (tmp_path / "x").exists()


# ----------------------------------------------------------------------- 4. GEFS

#: A condensed but faithful GEFS pgrb2a inventory for one member: the family
#: fields, the averaged cloud with its window in the forecast token, and the
#: records the family scope leaves behind.
GEFS_IDX = "\n".join(
    f"{number}:{number * 200_000}:d=2026090100:{param}:{level}:{forecast}:"
    for number, (param, level, forecast) in enumerate(
        (
            ("PRMSL", "mean sea level", "24 hour fcst"),
            ("TMP", "2 m above ground", "24 hour fcst"),
            ("DPT", "2 m above ground", "24 hour fcst"),
            ("RH", "2 m above ground", "24 hour fcst"),
            ("UGRD", "10 m above ground", "24 hour fcst"),
            ("VGRD", "10 m above ground", "24 hour fcst"),
            ("TCDC", "entire atmosphere", "18-24 hour ave fcst"),
            ("TCDC", "475 mb", "24 hour fcst"),
            ("HGT", "cloud ceiling", "24 hour fcst"),
            ("RH", "850 mb", "24 hour fcst"),
        ),
        start=1,
    )
)

#: The same inventory with the cloud record's window token removed, which is the
#: case the spec says must not be stored.
GEFS_IDX_UNSTATED_WINDOW = GEFS_IDX.replace("18-24 hour ave fcst", "24 hour fcst")


def gefs_reader(path, *, upstream: str, member: str, bounds):
    keys = {
        "PRMSL:mean sea level": "mean_sea_level_pressure",
        "TMP:2 m above ground": "temperature_2m",
        "DPT:2 m above ground": "dew_point_2m",
        "RH:2 m above ground": "relative_humidity_2m",
        "UGRD:10 m above ground": "wind_u_10m",
        "VGRD:10 m above ground": "wind_v_10m",
        "TCDC:entire atmosphere (n-n+6 hour ave fcst)": "total_cloud_mean_6h",
    }
    return member_field(UNITS_BY_KEY[keys[upstream]])


def gefs_candidate() -> RunCandidate:
    return RunCandidate(
        provider_run_id="gefs-2026090100",
        run_time=datetime(2026, 9, 1, tzinfo=UTC),
        detail={"date_str": "20260901", "cycle": "00", "lead_hours": 24},
    )


def gefs_client(idx: str = GEFS_IDX) -> FakeClient:
    adapter = NOAAGEFSEnsembleAdapter()
    members = gefs_member_identifiers(get_config("noaa-gefs").ensemble)
    return FakeClient(
        texts={
            f"{adapter.member_url(gefs_candidate(), member)}.idx": idx
            for member in members
        }
    )


def test_gefs_members_are_the_providers_own_file_names():
    members = gefs_member_identifiers(get_config("noaa-gefs").ensemble)
    assert members[0] == "gec00"  # the control, its own file
    assert members[1] == "gep01" and members[-1] == "gep30"
    assert len(members) == 31


def test_gefs_selection_is_restricted_to_the_catalogue_family_fields():
    selection = select_gefs_member_records(GEFS_IDX)
    stored = {upstream for _range, upstream, _label in selection.wanted}
    assert stored == {
        "PRMSL:mean sea level",
        "TMP:2 m above ground",
        "DPT:2 m above ground",
        "RH:2 m above ground",
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "TCDC:entire atmosphere (n-n+6 hour ave fcst)",
    }
    # The instantaneous 475 mb cloud, the ceiling and the pressure-level
    # humidity are published and outside the family scope; matching TCDC alone
    # would have pulled the isobaric record too.
    assert "TCDC:475 mb" in selection.published
    assert "TCDC:475 mb" not in stored
    assert "HGT:cloud ceiling" in selection.published


def test_gefs_stamps_the_averaging_window_from_the_records_own_label(tmp_path: Path):
    adapter = NOAAGEFSEnsembleAdapter(client=gefs_client(), reader=gefs_reader)
    result = adapter.assemble(gefs_candidate(), window_at(), tmp_path)

    selection = select_gefs_member_records(GEFS_IDX)
    label = next(
        label
        for _range, upstream, label in selection.wanted
        if upstream.startswith("TCDC:entire atmosphere")
    )
    assert label == "18-24 hour ave fcst"
    assert result.qc_passed is True  # a stamped window is not a QC failure

    stored = open_artifact(result.artifacts[0].payload_path)
    cloud = stored["total_cloud_mean_6h"]
    assert cloud.attrs["cell_methods"] == "time: mean"
    assert float(cloud.attrs["averaging_window_hours"]) == 6.0
    assert cloud.attrs["averaging_window_basis"] == "18-24 hour ave fcst"
    assert "total_cloud_geometric" not in stored  # never under the instantaneous key


def test_gefs_does_not_store_an_average_whose_window_the_record_leaves_unstated(
    tmp_path: Path,
):
    adapter = NOAAGEFSEnsembleAdapter(
        client=gefs_client(GEFS_IDX_UNSTATED_WINDOW), reader=gefs_reader
    )
    result = adapter.assemble(gefs_candidate(), window_at(), tmp_path)

    provenance = result.artifacts[0].provenance
    assert provenance["unstorable_fields"], (
        "an unstated window must be reported, not stored"
    )
    assert "total_cloud_mean_6h" in provenance["storage_scope"]["not_retrieved"]
    stored = open_artifact(result.artifacts[0].payload_path)
    assert "total_cloud_mean_6h" not in stored


def test_gefs_lists_every_other_published_record_as_available_not_stored(
    tmp_path: Path,
):
    adapter = NOAAGEFSEnsembleAdapter(client=gefs_client(), reader=gefs_reader)
    result = adapter.assemble(gefs_candidate(), window_at(), tmp_path)

    scope = result.artifacts[0].provenance["storage_scope"]
    assert scope["applied"] == "family_fields_only"
    assert "TCDC:475 mb" in scope["available_not_stored"]
    assert "HGT:cloud ceiling" in scope["available_not_stored"]
    assert scope["not_retrieved"] == []  # every field inside the scope arrived


def test_gefs_publishes_one_member_axis_with_the_control_flagged(tmp_path: Path):
    adapter = NOAAGEFSEnsembleAdapter(client=gefs_client(), reader=gefs_reader)
    result = adapter.assemble(gefs_candidate(), window_at(), tmp_path)

    members = result.artifacts[0].provenance["members"]
    assert members["declared"] == 31
    assert len(members["present"]) == 31
    assert members["control"] == "gec00"
    assert members["control_retrieval"] == "separate_file"  # one file per member
    stored = open_artifact(result.artifacts[0].payload_path)
    flags = stored[CONTROL_COORD].values
    assert flags.sum() == 1  # exactly the control, never a defaulted member
    assert stored[MEMBER_DIM].values[flags][0] == "gec00"


def test_gefs_selected_loader_runs_existing_decoder_and_cache_once(tmp_path: Path):
    from datetime import timedelta
    from weather_api.gefs_query import GEFS_FIELDS, GEFSRequestKey, GEFSQueryService, GEFSSelectedLoader, demand_operation_bounds
    adapter = NOAAGEFSEnsembleAdapter(client=gefs_client(), reader=gefs_reader)
    run = datetime(2026, 9, 1, tzinfo=UTC)
    members = gefs_member_identifiers(get_config("noaa-gefs").ensemble)
    key = GEFSRequestKey("2026090100", run, 24, "pgrb2ap5", members, GEFS_FIELDS,
                         (("east", -40.0), ("north", 55.0), ("south", 40.0), ("west", -70.0)))
    loads = []
    loader = GEFSSelectedLoader(adapter, tmp_path)
    service = GEFSQueryService(lambda request: loads.append(request) or loader(request),
                               workspace=tmp_path, preflight=lambda _workspace: demand_operation_bounds())
    first = service.query(key)
    second = service.query(key)
    assert second is first and loads == [key]
    assert first.members_present == members and first.mandatory_failures == {}
    assert first.optional_absences == {}
    assert set(first.cloud_intervals) == set(members)
    assert set(first.cloud_intervals.values()) == {(run + timedelta(hours=18), run + timedelta(hours=24))}
    assert first.complete is True and first.backing_bytes > len(first.payload)
