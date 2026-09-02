#!/usr/bin/env python3
"""Validate, audit, and export the experimental source registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from source_data import registry  # noqa: E402

ALLOWED_STATUSES = {
    "active", "implementing", "credential_required", "licence_review",
    "unavailable", "duplicate_evidence", "unsupported_field", "retired", "rejected",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def delivery_kind_errors(source: dict[str, Any]) -> list[str]:
    """Enforce what a declared delivery kind must carry.

    A record may declare ``intermediary_derived`` for values an intermediary
    computed from a producer's retrieved fields by the intermediary's own
    method - values the producer never published. Such a record must name the
    producer, the intermediary as distinct from the producer, and the
    intermediary's method where the intermediary documents one; and it must say
    which of its fields carry the kind, because one intermediary may deliver
    reprocessed and intermediary-derived fields for the same producer. A record
    that declares the kind and names no intermediary fails here, so it is never
    schedulable.
    """
    errors: list[str] = []
    sid = source["id"]
    kind = source.get("delivery_kind")
    intermediary = source.get("intermediary")
    per_field = source.get("field_delivery_kinds")

    if intermediary is not None and kind not in {"reprocessed", "intermediary_derived"}:
        errors.append(f"{sid}: names an intermediary but its delivery kind is {kind!r}")
    if per_field is not None and kind is None:
        errors.append(f"{sid}: declares per-field delivery kinds without a record-level delivery kind")

    if kind == "intermediary_derived":
        name = (intermediary or {}).get("name", "")
        if not name:
            errors.append(f"{sid}: declares intermediary_derived and names no intermediary")
        elif name.strip().lower() == source["producer"].strip().lower():
            errors.append(f"{sid}: intermediary must be distinct from the producer")
        if not source["producer"].strip():
            errors.append(f"{sid}: declares intermediary_derived and names no producer")
        if not per_field or "intermediary_derived" not in per_field.values():
            errors.append(f"{sid}: declares intermediary_derived and names no field that carries it")

    if per_field:
        published = {name for group in source["variables"] for name in group["names"]}
        for field_name, field_kind in sorted(per_field.items()):
            if field_name not in published:
                errors.append(f"{sid}: field_delivery_kinds names {field_name!r}, which the record does not publish")
            if field_kind == "intermediary_derived" and kind != "intermediary_derived":
                errors.append(f"{sid}: field {field_name!r} is intermediary_derived but the record is not")
    return errors


def semantic_errors(data: dict[str, Any], coverage: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = data["sources"]
    ids = [source["id"] for source in sources]
    known = set(ids)
    if len(ids) != len(known):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        errors.append(f"duplicate source ids: {', '.join(duplicates)}")

    referenced: set[str] = set()
    for candidate, source_ids in coverage["plan_candidates"].items():
        if not source_ids:
            errors.append(f"catalogue candidate has no mappings: {candidate}")
        for source_id in source_ids:
            referenced.add(source_id)
            if source_id not in known:
                errors.append(f"catalogue candidate {candidate!r} references unknown id {source_id!r}")
    unreferenced = sorted(known - referenced)
    if unreferenced:
        errors.append(f"registry sources absent from catalogue coverage: {', '.join(unreferenced)}")

    for source in sources:
        sid = source["id"]
        status = source["status"]
        if status not in ALLOWED_STATUSES:
            errors.append(f"{sid}: invalid status {status!r}")
        auth = source["authentication"]
        if status == "credential_required" and not auth["required"]:
            errors.append(f"{sid}: credential_required must set authentication.required=true")
        if auth["required"] and not auth["registration_url"]:
            errors.append(f"{sid}: authenticated source needs an official registration URL")
        if status in {"retired", "unavailable", "rejected"}:
            if source["fixture_status"] != "not_applicable" or source["live_smoke_test_status"] != "not_applicable":
                errors.append(f"{sid}: terminal status must mark fixture and live tests not_applicable")
        if status == "active" and (source["fixture_status"] != "passing" or source["live_smoke_test_status"] != "passing"):
            errors.append(f"{sid}: active requires passing fixture and live smoke tests")
        if source["consensus"]["eligible"]:
            if not source["consensus"]["family"]:
                errors.append(f"{sid}: consensus-eligible source needs an independent-centre family")
            if source["category"] != "deterministic_forecast":
                errors.append(f"{sid}: only deterministic_forecast records may be centre representatives")
        errors.extend(delivery_kind_errors(source))
        serialized = json.dumps(source).lower()
        for marker in ("api_key=", "apikey=", "password=", "bearer ey"):
            if marker in serialized:
                errors.append(f"{sid}: possible credential material in registry")
    return errors


def validate(data: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    data = data or registry()
    schema = load_json(HERE / "schema.json")
    coverage = load_json(HERE / "catalogue_coverage.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = [f"schema {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}" for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))]
    errors.extend(semantic_errors(data, coverage))
    return data, errors


def summary(data: dict[str, Any]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    categories: dict[str, int] = {}
    delivery_kinds: dict[str, int] = {}
    for source in data["sources"]:
        statuses[source["status"]] = statuses.get(source["status"], 0) + 1
        categories[source["category"]] = categories.get(source["category"], 0) + 1
        declared = source.get("delivery_kind", "undeclared")
        delivery_kinds[declared] = delivery_kinds.get(declared, 0) + 1
    return {
        "registry_version": data["registry_version"],
        "as_of": data["as_of"],
        "source_count": len(data["sources"]),
        "status_counts": dict(sorted(statuses.items())),
        "category_counts": dict(sorted(categories.items())),
        "consensus_representatives": sorted(source["id"] for source in data["sources"] if source["consensus"]["eligible"]),
        # Listed by id rather than counted: a record whose values an
        # intermediary computed is the one a reader of the summary most needs
        # to be able to name.
        "delivery_kind_counts": dict(sorted(delivery_kinds.items())),
        "intermediary_derived_sources": sorted(
            source["id"] for source in data["sources"] if source.get("delivery_kind") == "intermediary_derived"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="write the fully materialized registry JSON to stdout")
    parser.add_argument("--summary-json", action="store_true", help="write audit summary JSON to stdout")
    args = parser.parse_args(argv)
    data, errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.export:
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        print()
    elif args.summary_json:
        json.dump(summary(data), sys.stdout, indent=2, sort_keys=True)
        print()
    else:
        report = summary(data)
        print(f"registry valid: {report['source_count']} sources, version {report['registry_version']}, as of {report['as_of']}")
        print("statuses: " + ", ".join(f"{key}={value}" for key, value in report["status_counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
