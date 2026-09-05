"""The four ensemble access shapes, one adapter each, no network.

Every family here is declared **not schedulable**, so none of these adapters has
ever run against its upstream. The fixtures below are therefore the whole of the
evidence: fake ``.idx`` and ``.index`` text in the producers' own shapes (taken
from ``docs/research/wayfinder/ensemble-access.md``), fake clients that answer
from those strings, and injected readers that stand in for the GRIB and GeoTIFF
decoders. What is being pinned is the part that does not depend on decoding: the
member identifiers, the request shapes, the two-file assembly, the storage scope
and the refusal to schedule.

Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/artifact-ingestion/spec.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy
import pytest
import xarray
import zarr

from ingest.adapters import eccc_geomet_ensemble as reps_module
from ingest.adapters.eccc_geomet_ensemble import (
    ECCCREPSEnsembleAdapter,
    REPS_EVIDENCE_BOX,
    REPS_SCALESIZE,
    control_retrieval_for,
    coverage_id,
    coverage_params,
    coverage_url,
    declaration_for,
    member_identifiers,
    stored_member_coverages,
)
from ingest.adapters.ecmwf_opendata import (
    ECMWFAIFSEnsembleAdapter,
    ECMWFENSEnsembleAdapter,
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

UTC = timezone.utc

#: The four families this task builds, in the owner's declared build order.
BUILD_ORDER = ("eccc-reps", "ecmwf-aifs-ens", "ecmwf-ens", "noaa-gefs")


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

    def __init__(self, *, texts: dict[str, str] | None = None, missing: tuple[str, ...] = ()) -> None:
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

    def get_text(self, url: str) -> str:
        self.urls.append(url)
        self._check(url)
        if url in self.texts:
            return self.texts[url]
        raise FileNotFoundError(f"no fixture text for {url}")

    def download_ranges(self, url: str, destination: Path, ranges, *, max_bytes: int) -> int:
        self.urls.append(url)
        self._check(url)
        self.ranges.append((url, list(ranges)))
        destination.write_bytes(b"GRIB-stub")
        return sum(end - start + 1 for start, end in self.ranges[-1][1])


def window_at(moment: datetime = datetime(2026, 9, 2, 12, tzinfo=UTC)) -> FetchWindow:
    return FetchWindow(now=moment)


def open_artifact(payload_path: Path) -> xarray.Dataset:
    """The staged artifact, read back the way the store reads it."""
    return xarray.open_zarr(zarr.storage.ZipStore(str(payload_path), mode="r"), consolidated=False)


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
        assert config.ingestible is False, f"{source_id} became schedulable by being adapted"


@pytest.mark.parametrize(
    "adapter",
    [
        ECCCREPSEnsembleAdapter(),
        ECMWFAIFSEnsembleAdapter(),
        ECMWFENSEnsembleAdapter(),
        NOAAGEFSEnsembleAdapter(),
    ],
)
def test_discovery_refuses_while_the_registry_says_the_family_is_not_schedulable(adapter):
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
    assert ("SCALESIZE", REPS_SCALESIZE) in params  # native resolution, mandatory
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
    assert declaration.control.identifier is None  # and none of them is named the control
    assert control_retrieval_for(declaration) is None


def reps_adapter(client: FakeClient) -> ECCCREPSEnsembleAdapter:
    def reader(payload: bytes, *, coverage: str):
        key = next(
            key for key, template in stored_member_coverages("eccc-reps")
            if coverage.startswith(template.split("<")[0])
        )
        return member_field(UNITS_BY_KEY[key])

    return ECCCREPSEnsembleAdapter(client=client, reader=reader)


def test_reps_stores_every_published_member_field_and_flags_no_control(tmp_path: Path):
    client = FakeClient()
    result = reps_adapter(client).assemble(
        RunCandidate(provider_run_id="reps-2026090200", run_time=datetime(2026, 9, 2, tzinfo=UTC)),
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
    candidate = RunCandidate(provider_run_id="reps-2026090200", run_time=datetime(2026, 9, 2, tzinfo=UTC))
    adapter.assemble(candidate, window_at(), tmp_path)

    stacked = reps_module.stack_members(
        {member: member_field("percent") for member in member_identifiers(declaration_for("eccc-reps"))},
        control=None,
    )
    assert stacked.sizes[MEMBER_DIM] == 21
    assert not bool(stacked[CONTROL_COORD].values.any())


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
    def __init__(self, status: int, payload: bytes, content_range: str) -> None:
        self.status_code = status
        self.content = payload
        self.headers = {"Content-Range": content_range}

    def close(self) -> None:
        pass


def exact_range_client(response: ExactRangeResponse):
    client = object.__new__(__import__("ingest.http", fromlist=["PoliteClient"]).PoliteClient)
    client._request = lambda *_args, **_kwargs: response
    return client


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (ExactRangeResponse(200, b"whole", ""), "range_status"),
        (ExactRangeResponse(206, b"12345", "bytes 0-5/100"), "range_length"),
        (ExactRangeResponse(206, b"123456", "bytes 1-6/100"), "range_content_range"),
    ],
)
def test_ecmwf_exact_range_refuses_full_body_short_body_and_wrong_identity(
    tmp_path: Path, response: ExactRangeResponse, reason: str
):
    with pytest.raises(ValueError, match=reason):
        _download_verified_range(exact_range_client(response), "https://example.test/run", tmp_path / "x", (0, 5))


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
        texts={f"{adapter.member_url(gefs_candidate(), member)}.idx": idx for member in members}
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
        label for _range, upstream, label in selection.wanted
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


def test_gefs_does_not_store_an_average_whose_window_the_record_leaves_unstated(tmp_path: Path):
    adapter = NOAAGEFSEnsembleAdapter(
        client=gefs_client(GEFS_IDX_UNSTATED_WINDOW), reader=gefs_reader
    )
    result = adapter.assemble(gefs_candidate(), window_at(), tmp_path)

    provenance = result.artifacts[0].provenance
    assert provenance["unstorable_fields"], "an unstated window must be reported, not stored"
    assert "total_cloud_mean_6h" in provenance["storage_scope"]["not_retrieved"]
    stored = open_artifact(result.artifacts[0].payload_path)
    assert "total_cloud_mean_6h" not in stored


def test_gefs_lists_every_other_published_record_as_available_not_stored(tmp_path: Path):
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
