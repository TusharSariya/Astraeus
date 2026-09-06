#!/usr/bin/env python3
"""Capture or replay bounded issue-82 ECMWF ensemble evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import xarray
import zarr
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.adapters.ecmwf_opendata import (  # noqa: E402
    ECMWFAIFSEnsembleAdapter,
    ECMWFENSEnsembleAdapter,
    IFS_CYCLE_50R1_CONTROL_MAPPING,
)
from ingest.contract import FetchWindow, RunCandidate  # noqa: E402
from ingest.http import PoliteClient  # noqa: E402
from weather_api.store import LiveStore  # noqa: E402

UTC = timezone.utc


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            value.update(chunk)
    return value.hexdigest()


class ReplayClient:
    """Serve exact indexed records from an immutable retained capture."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.receipt = json.loads((source / "receipt.json").read_text())
        for item in self.receipt["indexes"]:
            index = source / f"{item['label']}.index"
            if index.stat().st_size != item["bytes"] or digest(index) != item["sha256"]:
                raise AssertionError(f"retained index failed integrity: {index.name}")

    def get_text(self, url: str) -> str:
        label = next(
            item["label"] for item in self.receipt["indexes"] if item["url"] == url
        )
        return (self.source / f"{label}.index").read_text()

    def download_ranges(self, url, destination, ranges, *, max_bytes):
        assert len(ranges) == 1
        wanted = list(ranges[0])
        item = next(
            entry
            for entry in self.receipt["ranges"]
            if entry["url"] == url and entry["range"] == wanted
        )
        source = self.source / item["path"]
        if (
            source.stat().st_size > max_bytes
            or source.stat().st_size != item["byte_size"]
            or digest(source) != item["sha256"]
        ):
            raise AssertionError(f"retained range failed integrity: {item['path']}")
        shutil.copyfile(source, destination)
        self.last_response_evidence = {
            "http_status": item["http_status"],
            "content_range": item["content_range"],
        }
        return source.stat().st_size


class RetainedPerturbedAndLiveControlClient:
    """Replay retained IFS perturbed records and fetch only the mapped control."""

    def __init__(self, perturbed: Path) -> None:
        self.replay = ReplayClient(perturbed)
        self.live = PoliteClient()
        self.perturbed = perturbed
        self.last_response_evidence: dict[str, object] = {}

    def get_text(self, url: str) -> str:
        if "/enfo/" in url:
            return self.replay.get_text(url)
        return self.live.get_text(url)

    def download_ranges(self, url, destination, ranges, *, max_bytes):
        if "/enfo/" in url:
            size = self.replay.download_ranges(url, destination, ranges, max_bytes=max_bytes)
            self.last_response_evidence = dict(self.replay.last_response_evidence)
            return size
        start, end = ranges[0]
        response = self.live._request(
            "GET", url, headers={"Range": f"bytes={start}-{end}"}, stream=True
        )
        try:
            content_range = response.headers.get("Content-Range", "")
            if response.status_code != 206:
                raise AssertionError(f"live control range status {response.status_code}")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
            if (
                match is None
                or int(match.group(1)) != start
                or int(match.group(2)) != end
                or int(match.group(3)) <= end
            ):
                raise AssertionError(f"live control Content-Range mismatch: {content_range!r}")
            declared = response.headers.get("Content-Length", "")
            if declared and (not declared.isdigit() or int(declared) != end - start + 1):
                raise AssertionError(f"live control Content-Length mismatch: {declared!r}")
            payload = response.read()
            if len(payload) != end - start + 1:
                raise AssertionError("live control range length mismatch")
            destination.write_bytes(payload)
            self.last_response_evidence = {
                "http_status": response.status_code,
                "content_range": content_range,
            }
            return len(payload)
        finally:
            response.close()


def candidate(source_id: str, stamp: str, lead: int) -> RunCandidate:
    run = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    model = "aifs-ens" if source_id == "ecmwf-aifs-ens" else "ifs"
    suffix = "pf" if source_id == "ecmwf-aifs-ens" else "ef"
    directory = f"https://data.ecmwf.int/forecasts/{stamp[:8]}/{stamp[8:10]}z/{model}/0p25/enfo"
    member_url = f"{directory}/{stamp}-{lead}h-enfo-{suffix}.grib2"
    detail = {"member_url": member_url, "lead_hours": lead}
    urls = [member_url]
    if source_id == "ecmwf-aifs-ens":
        control_url = f"{directory}/{stamp}-{lead}h-enfo-cf.grib2"
        detail["control_url"] = control_url
        urls.append(control_url)
    return RunCandidate(f"{source_id}-{stamp}-f{lead:03d}", run, urls, detail)


def readback(artifact, result, output: Path, *, retrieved_at: datetime) -> dict[str, object]:
    path = artifact.payload_path
    valid_time = datetime.fromisoformat(artifact.provenance["valid_time"])
    artifact_sha256 = digest(path)
    artifact.provenance["sha256"] = artifact_sha256

    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with path.open("rb") as source: shutil.copyfileobj(source, handle)

    record = SimpleNamespace(
        revision_id=f"issue-82-test-only-{result.source_id}", source_id=result.source_id,
        logical_name=artifact.logical_name, media_type=artifact.media_type,
        object_key="retained-local-proof", byte_size=path.stat().st_size,
        sha256=artifact_sha256, provenance=artifact.provenance, run_time=result.run_time,
        retrieved_at=retrieved_at, native_crs=result.native_crs,
    )

    class Store:
        s3 = S3()
        config = SimpleNamespace(bucket="issue-82-test-only")
        def current_artifacts(self): return [record]

    store = LiveStore(Store(), output / ".reader-cache")
    api = FastAPI()

    @api.get("/evidence")
    def evidence(member: str):
        values = store.sample_point(
            47.5, -52.75, valid_time, member=member
        )
        return {"operational": False, "member": member, "values": [
            {"variable": item.variable, "value": item.value, "units": item.units}
            for item in values
        ]}

    client = TestClient(api)
    zarr_store = zarr.storage.ZipStore(str(path), mode="r")
    dataset = xarray.open_zarr(zarr_store, consolidated=False)
    members = [str(item) for item in dataset.member.values.tolist()]
    expected = [*members, "999"]
    responses = {}
    for member in expected:
        response = client.get("/evidence", params={"member": member})
        if response.status_code != 200:
            raise AssertionError(f"API readback failed for member {member}: {response.status_code}")
        responses[member] = {"status": response.status_code, "body": response.json()}
    direct = dataset.sel(latitude=47.5, longitude=-52.75, method="nearest").sel(
        valid_time=valid_time.replace(tzinfo=None)
    )
    for member in members:
        values = {
            item["variable"]: item for item in responses[member]["body"]["values"]
        }
        if set(values) != set(map(str, dataset.data_vars)):
            raise AssertionError(f"HTTP field set differs for member {member}")
        for variable, field in dataset.data_vars.items():
            expected_value = float(direct[variable].sel(member=member).values)
            actual = values[str(variable)]
            if not math.isfinite(expected_value):
                if actual["value"] is not None:
                    raise AssertionError(f"masked value became numeric: {member}:{variable}")
            elif actual["value"] is None or not math.isclose(
                actual["value"], expected_value, rel_tol=0, abs_tol=1e-6
            ):
                raise AssertionError(f"HTTP/artifact value mismatch: {member}:{variable}")
            if actual["units"] != field.attrs.get("units"):
                raise AssertionError(f"HTTP/artifact units mismatch: {member}:{variable}")
    if responses["999"]["body"]["values"]:
        raise AssertionError("unknown member returned values")
    zarr_store.close()
    shutil.rmtree(output / ".reader-cache", ignore_errors=True)
    return responses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--offline", type=Path)
    parser.add_argument("--stamp", default="20260905000000")
    parser.add_argument("--lead", type=int, default=24)
    parser.add_argument("--family", choices=("all", "aifs", "ifs"), default="all")
    parser.add_argument("--ifs-perturbed-from", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    retained = args.offline.resolve() if args.offline else None
    if retained and (output.is_relative_to(retained) or retained.is_relative_to(output)):
        parser.error("offline replay input and output must not contain one another")
    if output.exists() and any(output.iterdir()):
        parser.error("output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    replayed_at = datetime.now(UTC)
    summary = {"replayed_at": replayed_at.isoformat() if retained else None,
               "operational": False, "sources": []}

    classes = {
        "aifs": (ECMWFAIFSEnsembleAdapter,),
        "ifs": (ECMWFENSEnsembleAdapter,),
        "all": (ECMWFAIFSEnsembleAdapter, ECMWFENSEnsembleAdapter),
    }[args.family]
    for cls in classes:
        source_id = cls.source_id
        source = output / source_id
        source.mkdir()
        retained_source = retained / source_id if retained else None
        hybrid_source = args.ifs_perturbed_from.resolve() if (
            source_id == "ecmwf-ens" and args.ifs_perturbed_from
        ) else None
        if retained_source:
            receipt = json.loads((retained_source / "receipt.json").read_text())
            stamp, lead = receipt["stamp"], receipt["lead_hours"]
            retained_time = receipt.get("retrieved_at") or receipt.get("captured_at")
            if not retained_time:
                raise AssertionError(f"retained receipt has no retrieval time: {source_id}")
            original_retrieved_at = datetime.fromisoformat(retained_time)
            client = ReplayClient(retained_source)
            retain_inputs = False
        elif hybrid_source:
            prior_receipt = json.loads((hybrid_source / "receipt.json").read_text())
            stamp, lead = prior_receipt["stamp"], prior_receipt["lead_hours"]
            original_retrieved_at = datetime.fromisoformat(prior_receipt["retrieved_at"])
            client = RetainedPerturbedAndLiveControlClient(hybrid_source)
            retain_inputs = True
        else:
            stamp, lead = args.stamp, args.lead
            original_retrieved_at = None
            client = PoliteClient()
            retain_inputs = True
        run_candidate = candidate(source_id, stamp, lead)
        if retained_source and any("/oper/" in item["url"] for item in receipt["ranges"]):
            mapped_url = next(item["url"] for item in receipt["ranges"] if "/oper/" in item["url"])
            run_candidate.detail.update({
                "control_url": mapped_url,
                "ifs_cycle_50r1_control_mapping": {
                    **IFS_CYCLE_50R1_CONTROL_MAPPING,
                    "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
                },
            })
            run_candidate.urls.append(mapped_url)
        if hybrid_source:
            oper_directory = (
                f"https://data.ecmwf.int/forecasts/{stamp[:8]}/{stamp[8:10]}z/ifs/0p25/oper"
            )
            control_url = f"{oper_directory}/{stamp}-{lead}h-oper-fc.grib2"
            run_candidate.detail.update({
                "control_url": control_url,
                "ifs_cycle_50r1_control_mapping": {
                    **IFS_CYCLE_50R1_CONTROL_MAPPING,
                    "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
                },
            })
            run_candidate.urls.append(control_url)
        run = run_candidate.run_time
        window = FetchWindow(run + timedelta(hours=lead), back_hours=0, forward_hours=0)
        adapter = cls(client=client, retain_inputs=retain_inputs)
        result = adapter.assemble(run_candidate, window, source)
        captured_at = datetime.now(UTC)
        artifact = result.artifacts[0]
        if retained_source:
            expected = json.loads((retained_source / "receipt.json").read_text())["artifact"]
            if artifact.payload_path.stat().st_size != expected["bytes"] or digest(artifact.payload_path) != expected["sha256"]:
                raise AssertionError(f"offline artifact differs: {source_id}")
        ranges = []
        captured_ranges = {
            (item["url"], tuple(item["range"])): item
            for item in (receipt["ranges"] if retained_source else [])
        }
        if hybrid_source:
            captured_ranges.update({
                (item["url"], tuple(item["range"])): item
                for item in prior_receipt["ranges"]
            })
        for item in artifact.provenance["upstream_ranges"]:
            label = (
                "oper-fc-control0" if "/oper/" in item["url"]
                else "cf" if "-cf.grib2" in item["url"]
                else "pf" if "-pf.grib2" in item["url"]
                else "ef"
            )
            raw_name = f"{label}.{item['member']}.{item['parameter']}.source.grib2"
            raw = (retained_source if retained_source else source) / raw_name
            if not raw.is_file() or raw.stat().st_size != item["byte_size"] or digest(raw) != item["sha256"]:
                raise AssertionError(f"raw receipt mismatch: {raw_name}")
            prior = captured_ranges.get((item["url"], tuple(item["range"])), {})
            response = {
                key: item[key] if key in item else prior[key]
                for key in ("http_status", "content_range")
                if key in item or key in prior
            }
            if set(response) != {"http_status", "content_range"}:
                raise AssertionError(f"missing verified HTTP response identity: {raw_name}")
            range_captured_at = prior.get("captured_at")
            if hybrid_source and not range_captured_at:
                range_captured_at = (
                    prior_receipt["retrieved_at"] if "/enfo/" in item["url"]
                    else result.retrieved_at.isoformat()
                )
            ranges.append({
                **item,
                "path": raw_name,
                **response,
                **({"captured_at": range_captured_at} if range_captured_at else {}),
            })
        indexes = []
        labels = ({"pf", "cf"} if source_id == "ecmwf-aifs-ens" else {"ef"})
        if hybrid_source:
            labels = {"ef", "oper-fc-control0"}
        elif retained_source:
            labels = {item["label"] for item in receipt["indexes"]}
        for label in labels:
            index = (retained_source if retained_source else source) / f"{label}.index"
            index_url = next(item["url"] for item in ranges if item["path"].startswith(f"{label}."))
            indexes.append({"label": label, "url": index_url.removesuffix(".grib2") + ".index",
                            "bytes": index.stat().st_size, "sha256": digest(index)})
        receipt = {"source_id": source_id, "stamp": stamp, "lead_hours": lead,
                   "retrieved_at": (
                       retained_time
                       if retained_source else result.retrieved_at.isoformat()
                   ),
                   "assembled_at": captured_at.isoformat(),
                   "input_captures": (receipt.get("input_captures", {}) if retained_source else {
                       "perturbed": {
                           "retrieved_at": prior_receipt["retrieved_at"],
                           "source": "retained ecmwf-ensemble-20260905-corrective/ecmwf-ens",
                           "receipt_sha256": digest(hybrid_source / "receipt.json"),
                       },
                       "mapped_control": {"retrieved_at": captured_at.isoformat(), "source": "anonymous ECMWF HTTPS"},
                   } if hybrid_source else {}),
                   "indexes": sorted(indexes, key=lambda item: item["label"]), "ranges": ranges,
                   "result": {"complete": result.complete, "qc_passed": result.qc_passed,
                              "members": artifact.provenance["members"], "quality": artifact.provenance["quality"]},
                   "artifact": {"path": artifact.payload_path.name, "bytes": artifact.payload_path.stat().st_size,
                                "sha256": digest(artifact.payload_path)}}
        (source / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        api = readback(
            artifact, result, source,
            retrieved_at=original_retrieved_at or result.retrieved_at,
        )
        (source / "api-readback.json").write_text(json.dumps(api, indent=2, sort_keys=True) + "\n")
        summary["sources"].append({"source_id": source_id, "complete": result.complete,
                                   "qc_passed": result.qc_passed, "range_count": len(ranges),
                                   "upstream_bytes": sum(item["byte_size"] for item in ranges),
                                   "retrieved_at": receipt["retrieved_at"],
                                   "artifact": receipt["artifact"], "offline_replay": bool(retained)})
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
