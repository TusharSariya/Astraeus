#!/usr/bin/env python3
"""Validate, audit, and export the experimental source registry and field catalogue."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fields as field_catalogue  # noqa: E402
from source_data import registry  # noqa: E402

ALLOWED_STATUSES = {
    "active", "implementing", "credential_required", "licence_review",
    "unavailable", "duplicate_evidence", "unsupported_field", "retired", "rejected",
}

#: Where adapter manifests live. Read statically rather than imported: the audit
#: must run in CI without numpy, xarray or a network stack, and an adapter that
#: cannot be imported must still have its declared keys checked.
INGEST_ROOT = HERE.parent / "ingest"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def declared_field_keys(root: Path = INGEST_ROOT) -> dict[str, list[str]]:
    """Every literal field key an adapter manifest declares, by file.

    Parsed out of the source rather than imported, so this stays a cheap CI
    check. A key built at run time from a binding table is caught instead by the
    manifest validation in ``ingest.manifest``, which resolves against the same
    catalogue; what is checked here is every key an author wrote down.
    """
    found: dict[str, list[str]] = {}
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        keys: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "RequiredField":
                continue
            name: ast.expr | None = node.args[0] if node.args else None
            for keyword in node.keywords:
                if keyword.arg == "name":
                    name = keyword.value
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                keys.append(name.value)
        if keys:
            found[str(path.relative_to(root.parent))] = sorted(set(keys))
    return found


#: Categories whose every member carries forecast lead times, mirrored from
#: ``ingest.registry.FORECAST_CATEGORIES``. Copied rather than imported for the
#: same reason adapter manifests are parsed rather than imported: the audit must
#: run in CI without numpy, xarray or a network stack, and ``ingest.registry``
#: pulls in the adapter contract. ``test_reach.py`` asserts the two agree
#: whenever ``ingest`` is importable, so the copy cannot drift silently.
FORECAST_CATEGORIES = frozenset({
    "deterministic_forecast",
    "ensemble",
    "postprocessed_forecast",
    "nowcasting",
    "land_surface_forecast",
    "ocean",
    "wave",
    "surge",
    "marine",
})

_RUN_HOURS = {f"{hour:02d}" for hour in range(24)}


def adapter_source_ids(root: Path = INGEST_ROOT) -> set[str]:
    """Every source id an adapter module names as a string literal.

    Parsed statically out of ``ingest/adapters/*.py``, exactly as
    ``declared_field_keys`` parses field keys and for the same reason: an
    adapter that cannot be imported here must still have its registry record
    checked. Both the class attribute (``source_id = "eccc-radar"``) and the
    constructor keyword (``source_id="eccc-hrdps"``) are read. The empty string
    is ignored: two base classes in ``eccc_geomet.py`` declare ``source_id =
    ""`` for a subclass to fill in, and an empty id is not a record.
    """
    found: set[str] = set()
    adapters = root / "adapters"
    if not adapters.is_dir():
        return found
    for path in sorted(adapters.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            values: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                if any(getattr(target, "id", None) == "source_id" for target in node.targets):
                    values.append(node.value)
            elif isinstance(node, ast.AnnAssign):
                if getattr(node.target, "id", None) == "source_id" and node.value is not None:
                    values.append(node.value)
            elif isinstance(node, ast.Call):
                values.extend(
                    keyword.value for keyword in node.keywords if keyword.arg == "source_id"
                )
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
                    found.add(value.value)
    return found


def _latency_errors(sid: str, latency: dict[str, Any]) -> list[str]:
    """A publication latency must say what it is and what stands behind it.

    The point of the block is that latency is measured, not promised. So a
    record may not claim an observation it does not have, and may not carry an
    estimate whose provenance it cannot name: a number with an empty basis, or
    a basis of ``"none"``, is a default that has been dressed as a
    measurement, which is the exact failure this change exists to stop.
    """
    errors: list[str] = []
    estimate = latency.get("estimate_seconds")
    count = latency.get("observation_count")
    last_observed = latency.get("last_observed")
    measured = latency.get("measured")
    basis = (latency.get("basis") or "").strip()

    if measured is False:
        if count != 0:
            errors.append(f"{sid}: publication_latency is not measured but claims {count} observations")
        if last_observed is not None:
            errors.append(f"{sid}: publication_latency is not measured but names a last observed instant")
    if measured is True:
        if not isinstance(count, int) or count < 1:
            errors.append(f"{sid}: publication_latency is measured but carries no observation")
        if not last_observed:
            errors.append(f"{sid}: publication_latency is measured but names no last observed instant")
    if estimate is None and measured is not False:
        errors.append(f"{sid}: publication_latency has no estimate but does not report measured false")
    if estimate is not None and (not basis or basis == "none"):
        errors.append(
            f"{sid}: publication_latency estimates {estimate} s with no basis; "
            "a defaulted latency is refused, state where the number came from"
        )
    return errors


def horizon_errors(data: dict[str, Any], adapter_ids: set[str] | None = None) -> list[str]:
    """Reach, cadence and latency, checked where a source can actually be run.

    A source that will not say how far it reaches cannot be shown to answer any
    instant, so every record with a registered adapter must declare a reach.
    Beyond that the shape follows the record's own kind: a forecast record is
    scheduled against a run and needs a run cadence and a latency block, an
    observation or nowcast record is scheduled against its own publication
    interval and needs a native cadence. The two are mutually exclusive, so a
    reader never has to guess which one a scheduler used.
    """
    errors: list[str] = []
    adapter_ids = adapter_source_ids() if adapter_ids is None else adapter_ids
    known = {source["id"] for source in data["sources"]}
    for source_id in sorted(adapter_ids - known):
        errors.append(f"{source_id}: an adapter registers this id but the registry has no such record")

    for source in data["sources"]:
        sid = source["id"]
        reach = source.get("reach")
        run_cadence = source.get("run_cadence_seconds")
        native_cadence = source.get("native_cadence_seconds")
        latency = source.get("publication_latency")
        forecast = source["category"] in FORECAST_CATEGORIES
        registered = sid in adapter_ids

        if registered and reach is None:
            errors.append(
                f"{sid}: has a registered adapter and declares no reach, so it is not schedulable "
                "and can be shown to cover no instant"
            )
        if registered and forecast:
            if not isinstance(run_cadence, int) or run_cadence <= 0:
                errors.append(f"{sid}: forecast record with a registered adapter declares no run cadence")
            if latency is None:
                errors.append(f"{sid}: forecast record with a registered adapter declares no publication_latency")
        if registered and not forecast:
            if not isinstance(native_cadence, int) or native_cadence <= 0:
                errors.append(f"{sid}: observation or nowcast record with a registered adapter declares no native cadence")

        if run_cadence is not None and native_cadence is not None:
            errors.append(f"{sid}: declares both a run cadence and a native cadence; a scheduler cannot use both")
        if forecast and native_cadence is not None:
            errors.append(f"{sid}: forecast record declares native_cadence_seconds, which belongs to observations")
        if not forecast and run_cadence is not None and sid in adapter_ids:
            errors.append(f"{sid}: non-forecast record declares run_cadence_seconds, which belongs to forecasts")

        if reach is not None:
            if reach["earliest_hours"] > reach["latest_hours"]:
                errors.append(f"{sid}: reach earliest_hours is after latest_hours")
            per_cycle = reach.get("per_cycle") or {}
            for hour, latest in sorted(per_cycle.items()):
                if hour not in _RUN_HOURS:
                    errors.append(f"{sid}: reach per_cycle key {hour!r} is not a two-digit UTC hour")
                if latest < reach["earliest_hours"]:
                    errors.append(f"{sid}: reach per_cycle {hour!r} ends before the record's earliest hour")
            if per_cycle:
                if not isinstance(run_cadence, int) or run_cadence <= 0:
                    errors.append(f"{sid}: reach states per_cycle but the record declares no run cadence to key it by")
                elif 86400 % run_cadence or len(per_cycle) != 86400 // run_cadence:
                    errors.append(
                        f"{sid}: reach states {len(per_cycle)} cycles but a {run_cadence} s run cadence "
                        f"means {86400 // run_cadence if not 86400 % run_cadence else '?'} runs a day"
                    )
        if latency is not None:
            errors.extend(_latency_errors(sid, latency))

        fallback = source.get("datamart_fallback_path")
        if fallback is not None:
            missing = [token for token in ("{YYYYMMDD}", "{HH}", "{FFF}") if token not in fallback]
            if missing:
                errors.append(
                    f"{sid}: datamart_fallback_path is missing {', '.join(missing)}; the working Datamart "
                    "layout is dated, /{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/, and a path without the "
                    "placeholders cannot address a run"
                )
    return errors


def catalogue_errors() -> list[str]:
    """Schema and semantic errors in the field catalogue, adapter keys included.

    The catalogue is the only source of field keys, so a key an adapter declares
    that the catalogue lacks is an error here and not only at publication time:
    an adapter whose manifest cannot validate is not schedulable, and CI is
    where that should be found.
    """
    data = field_catalogue.catalogue()
    schema = load_json(HERE / "fields.schema.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = [
        f"catalogue schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    ]
    declared = declared_field_keys()
    errors.extend(
        field_catalogue.validate_catalogue(
            adapter_keys=[key for keys in declared.values() for key in keys]
        )
    )
    return errors


def delivery_kind_errors(source: dict[str, Any]) -> list[str]:
    """Enforce what a record's delivery kind must carry.

    Every record declares how its values reach this deployment, because a
    value whose provenance cannot say whether it is the producer's own cell is
    not evidence anyone can weigh. ``published_cell`` is the producer's own
    grid or observation, retrieved from the producer or from a mirror that
    copies it byte for byte; ``reprocessed`` means an intermediary transformed
    the producer's field first, and must name that intermediary as distinct
    from the producer and state every transformation the intermediary
    documents. Only a ``published_cell`` record may be the display primary, and
    that is refused here rather than left to the display layer, which is where
    it was leaking from before.

    A record may also declare ``intermediary_derived`` for values an intermediary
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

    if kind is None:
        errors.append(f"{sid}: declares no delivery kind, so nothing downstream can say where its values came from")
    if intermediary is not None and kind not in {"reprocessed", "intermediary_derived"}:
        errors.append(f"{sid}: names an intermediary but its delivery kind is {kind!r}")
    if per_field is not None and kind is None:
        errors.append(f"{sid}: declares per-field delivery kinds without a record-level delivery kind")

    if kind == "reprocessed":
        name = (intermediary or {}).get("name", "")
        if not name:
            errors.append(f"{sid}: declares reprocessed and names no intermediary distinct from the producer")
        elif name.strip().lower() == source["producer"].strip().lower():
            errors.append(f"{sid}: intermediary must be distinct from the producer")
        if not (intermediary or {}).get("transformations"):
            errors.append(f"{sid}: declares reprocessed and states no transformation the intermediary documents")

    if source.get("display_primary") and kind != "published_cell":
        errors.append(
            f"{sid}: delivery kind {kind!r} may not be the display primary; only the producer's own cell may be"
        )

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
    errors.extend(horizon_errors(data))
    return errors


def validate(data: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    data = data or registry()
    schema = load_json(HERE / "schema.json")
    coverage = load_json(HERE / "catalogue_coverage.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = [f"schema {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}" for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))]
    errors.extend(semantic_errors(data, coverage))
    errors.extend(catalogue_errors())
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
        "not_display_primary": sorted(
            source["id"] for source in data["sources"] if not source.get("display_primary")
        ),
        # How many records can be shown to cover an instant at all, and how
        # many of the latencies behind the schedule are this deployment's own
        # measurement rather than a research seed. Today the measured count is
        # zero by construction, and it should be visible that it is.
        "reach_declared": sum(1 for source in data["sources"] if source.get("reach") is not None),
        "run_cadence_declared": sum(
            1 for source in data["sources"] if source.get("run_cadence_seconds") is not None
        ),
        "native_cadence_declared": sum(
            1 for source in data["sources"] if source.get("native_cadence_seconds") is not None
        ),
        "latency_measured": sorted(
            source["id"] for source in data["sources"]
            if (source.get("publication_latency") or {}).get("measured")
        ),
        "latency_seeded_unmeasured": sorted(
            source["id"] for source in data["sources"]
            if (source.get("publication_latency") or {}).get("estimate_seconds") is not None
            and not (source.get("publication_latency") or {}).get("measured")
        ),
        "adapter_source_ids": sorted(adapter_source_ids()),
        "catalogue": catalogue_summary(),
    }


def catalogue_summary() -> dict[str, Any]:
    """What the field catalogue holds, in the shape a reader can check at a glance."""
    data = field_catalogue.catalogue()
    declared = declared_field_keys()
    adapter_keys = sorted({key for keys in declared.values() for key in keys})
    return {
        "catalogue_version": data["catalogue_version"],
        "as_of": data["as_of"],
        "field_count": len(data["fields"]),
        "families": {name: len(field_catalogue.members(name)) for name in sorted(
            family["name"] for family in data["families"]
        )},
        "adapter_keys_declared": len(adapter_keys),
        "adapter_keys_resolved": sum(1 for key in adapter_keys if field_catalogue.has_field(key)),
        "available_not_stored": len(field_catalogue.available_not_stored()),
        "not_published": len(field_catalogue.not_published()),
        "sources_mapped": len(field_catalogue.mapped_sources()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="write the fully materialized registry JSON to stdout")
    parser.add_argument("--summary-json", action="store_true", help="write audit summary JSON to stdout")
    parser.add_argument("--export-catalogue", action="store_true", help="write the field catalogue JSON to stdout")
    args = parser.parse_args(argv)
    if args.export_catalogue:
        errors = catalogue_errors()
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        json.dump(field_catalogue.catalogue(), sys.stdout, indent=2, sort_keys=True)
        print()
        return 0
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
        print(
            f"horizon: {report['reach_declared']} records declare a reach "
            f"({report['run_cadence_declared']} run cadence, {report['native_cadence_declared']} native cadence) "
            f"across {len(report['adapter_source_ids'])} registered adapters; "
            f"{len(report['latency_seeded_unmeasured'])} latencies seeded, "
            f"{len(report['latency_measured'])} measured here"
        )
        catalogue = report["catalogue"]
        print(
            f"catalogue valid: {catalogue['field_count']} fields in {len(catalogue['families'])} "
            f"families, version {catalogue['catalogue_version']}, as of {catalogue['as_of']}"
        )
        print(
            f"adapter keys: {catalogue['adapter_keys_resolved']}/{catalogue['adapter_keys_declared']} resolved; "
            f"{catalogue['available_not_stored']} available-not-stored, "
            f"{catalogue['not_published']} not-published across {catalogue['sources_mapped']} sources"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
