#!/usr/bin/env python3
"""Validate, audit, and export the experimental source registry and field catalogue."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission  # noqa: E402
import fields as field_catalogue  # noqa: E402
from source_data import ENSEMBLE_BUILD_ORDER, registry  # noqa: E402

#: The state vocabulary is defined once, in ``registry/admission.py``, so that
#: the audit, the API ceiling and the ingest registry cannot drift apart.
ALLOWED_STATUSES = set(admission.STATES)

#: Where adapter manifests live. Read statically rather than imported: the audit
#: must run in CI without numpy, xarray or a network stack, and an adapter that
#: cannot be imported must still have its declared keys checked.
INGEST_ROOT = HERE.parent / "ingest"

#: The environment variable name shape a credential block may carry.
_CREDENTIAL_NAME = re.compile(r"^WEATHER_SECRET_[A-Z0-9_]+$")


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


#: The storage scope each subsettability declaration forces. A record does not
#: get to pick the pair: a path that subsets before the bytes leave the
#: producer stores everything it publishes, and a path that cannot subset pays
#: its whole file per record and so fetches only the catalogue's family fields.
_ENSEMBLE_SCOPE_FOR_SUBSETTING = {
    "server_side": "every_published_field",
    "none": "family_fields_only",
}


def ensemble_presence_errors(source: dict[str, Any]) -> list[str]:
    """The ``ensemble`` block is on every ensemble record and on no other.

    Both directions are refusals. A record categorised ``ensemble`` with no
    block declares a family whose member axis, control rule and storage scope
    nothing can check; a block on a record of any other category would put a
    member count and a control rule on a product that has neither, and would
    let a deterministic record be read as a family.
    """
    errors: list[str] = []
    sid = source["id"]
    block = source.get("ensemble")
    if source.get("category") == "ensemble" and block is None:
        errors.append(
            f"{sid}: category is ensemble and the record carries no ensemble block, so its "
            "member axis, control rule and storage scope are undeclared and uncheckable"
        )
    if block is not None and source.get("category") != "ensemble":
        errors.append(
            f"{sid}: carries an ensemble block but its category is {source.get('category')!r}; "
            "only an ensemble record declares a family"
        )
    return errors


def ensemble_scope_errors(sid: str, block: dict[str, Any]) -> list[str]:
    """No subsettability, no schedule: the storage scope has to follow from it.

    A record that will not say whether its access path subsets server side has
    a storage scope nobody can audit, so an undeclared or unrecognised
    ``subsetting`` is refused outright. Where it is declared, the scope is not
    a second judgement: ``server_side`` stores every published field and
    ``none`` stores the catalogue's family fields only. The pair is then
    checked against ``registry/fields.py`` ``SOURCE_SCOPE`` for the same id,
    because the catalogue's per-source policy and the family's declaration are
    two statements about one access path and a disagreement between them means
    one of the two is describing a path that does not exist.
    """
    errors: list[str] = []
    subsetting = block.get("subsetting")
    scope = block.get("storage_scope")
    if subsetting not in _ENSEMBLE_SCOPE_FOR_SUBSETTING:
        errors.append(
            f"{sid}: ensemble declares subsetting {subsetting!r}, which is neither 'server_side' "
            "nor 'none', so it is not schedulable and its storage scope cannot be checked"
        )
        return errors
    expected = _ENSEMBLE_SCOPE_FOR_SUBSETTING[subsetting]
    if scope != expected:
        errors.append(
            f"{sid}: ensemble subsetting {subsetting!r} forces storage_scope {expected!r}, "
            f"and the record declares {scope!r}"
        )
    catalogue_scope = field_catalogue.source_scope(sid)
    if catalogue_scope is None:
        errors.append(
            f"{sid}: ensemble declares a storage scope and the field catalogue records no "
            "SOURCE_SCOPE for the id, so the declaration stands against nothing"
        )
        return errors
    if catalogue_scope.subsetting != subsetting or catalogue_scope.policy != scope:
        errors.append(
            f"{sid}: ensemble declares subsetting {subsetting!r}/{scope!r} and the field "
            f"catalogue records {catalogue_scope.subsetting!r}/{catalogue_scope.policy!r}; "
            "the two describe one access path and may not disagree"
        )
    return errors


def ensemble_shape_errors(sid: str, block: dict[str, Any]) -> list[str]:
    """A member-shaped family declares its control; a reduction declares none.

    The control is a flag on the member axis, so a family that publishes
    members always declares the block and the rule by which the control is
    identified. The rule is what is required, not a non-null identifier:
    neither REPS nor ICON-EPS has a located control token, and a null
    ``control`` block would say those families publish no control, which is
    false and is what a reduction-only family declares. The prose then carries
    the honest statement that the control has not been located, and the
    verification fields keep the family unschedulable.

    A reduction-shaped family is the mirror image: no members, so no control,
    no member count, and a non-empty list of the provider statistics it
    publishes instead. A member-shaped family lists no reductions at all,
    because its provider's own reductions are a different product and are
    never mixed with a statistic over its member set.
    """
    errors: list[str] = []
    shape = block.get("shape")
    control = block.get("control")
    reductions = block.get("reductions")
    member_count = block.get("member_count")
    evidence = (block.get("verification") or {}).get("evidence")

    if shape == "members":
        if not isinstance(control, dict):
            errors.append(
                f"{sid}: ensemble declares members and no control block; a member-publishing "
                "family declares how its control is identified, and a null block says the "
                "family publishes no control"
            )
        elif not (control.get("rule") or "").strip():
            errors.append(
                f"{sid}: ensemble declares members and its control block states no rule; a "
                "null identifier is allowed where no measurement locates the control, but the "
                "rule that says so is not optional"
            )
        if reductions:
            errors.append(
                f"{sid}: ensemble declares members and lists provider reductions {reductions!r}; "
                "a member family's provider reductions are a different product"
            )
        # ``member_count`` is null exactly where nothing was measured at all
        # (design.md Seam A, widened by task 2.1). A family with an evidence
        # path states its count; ICON-EPS, measured nowhere, declares none
        # rather than inheriting another centre's EPS size.
        if evidence == "none" and member_count is not None:
            errors.append(
                f"{sid}: ensemble measured nothing (verification.evidence 'none') and declares "
                f"member_count {member_count!r}; a count that was assumed cannot be used to "
                "check completeness"
            )
        if evidence != "none" and member_count is None:
            errors.append(
                f"{sid}: ensemble declares members with an evidence path and no member_count, "
                "so completeness cannot be checked against anything"
            )
    elif shape == "reduction":
        if control is not None:
            errors.append(f"{sid}: ensemble declares reduction shape and a control; it publishes no members")
        if member_count is not None:
            errors.append(
                f"{sid}: ensemble declares reduction shape and member_count {member_count!r}; "
                "a reduction-only family publishes no member axis to count"
            )
        if not reductions:
            errors.append(
                f"{sid}: ensemble declares reduction shape and lists no reductions, so it "
                "declares neither members nor the statistics it publishes instead"
            )
    else:
        errors.append(f"{sid}: ensemble declares shape {shape!r}, which is neither 'members' nor 'reduction'")
    return errors


def ensemble_gap_errors(sid: str, block: dict[str, Any]) -> list[str]:
    """A declared gap may not also be declared published.

    A gap says the producer does not publish the field for this family, so the
    field is null with that reason and is never derived, borrowed or filled
    from the family's own provider reduction. If the field catalogue maps the
    same key for the same source as ``stored``, then one of the two records is
    wrong and a served value would not match any declaration, which the
    governing requirement refuses. ``available-not-stored`` is not the same
    claim and passes: GEFS declares ``total_cloud_geometric`` a gap for the
    column quantity while the catalogue records the single-level records it
    does publish as available and not fetched.
    """
    errors: list[str] = []
    for gap in block.get("gaps") or []:
        key = gap.get("field")
        if not key:
            errors.append(f"{sid}: ensemble declares a gap with no field name")
            continue
        if not (gap.get("reason") or "").strip():
            errors.append(f"{sid}: ensemble declares a gap on {key!r} with no reason")
        try:
            storage = field_catalogue.storage_of(sid, key)
        except field_catalogue.UnknownFieldKey:
            errors.append(f"{sid}: ensemble declares a gap on {key!r}, which is not a catalogue key")
            continue
        if storage == "stored":
            errors.append(
                f"{sid}: ensemble declares {key!r} a gap and the field catalogue maps it stored "
                "for the same source; a declared gap may not also be declared published"
            )
    return errors


def ensemble_verification_errors(sid: str, block: dict[str, Any]) -> list[str]:
    """Nothing unverified is schedulable, and nothing unmeasured is counted.

    A family carrying any ``unverified`` field, or naming no evidence at all,
    is not schedulable: a member count that was assumed cannot check
    completeness and an access path that was assumed cannot be run. The count
    clause is enforced in ``ensemble_shape_errors`` against the seam's
    biconditional (null iff reduction-shaped or nothing measured), because a
    count measured short of its control - IFS ENS observed 50 perturbed
    members and a documented control nobody located - is declared with its
    verification marked unverified rather than dropped; what that unverified
    mark forbids is scheduling the family, which is refused here.
    """
    errors: list[str] = []
    verification = block.get("verification") or {}
    unverified = sorted(
        name for name in ("member_count", "access_path", "cadence")
        if verification.get(name) != "verified"
    )
    evidence = verification.get("evidence")
    if block.get("schedulable"):
        if unverified:
            errors.append(
                f"{sid}: ensemble is schedulable with {', '.join(unverified)} unverified; a "
                "family is not schedulable beyond its own measured evidence"
            )
        if not evidence or evidence == "none":
            errors.append(
                f"{sid}: ensemble is schedulable and names no evidence, so nothing stands "
                "behind its member count, access path or cadence"
            )
        if verification.get("member_count") == "unverified" and block.get("member_count") is not None:
            errors.append(
                f"{sid}: ensemble is schedulable and its declared member_count is unverified, "
                "so completeness would be checked against an assumption"
            )
    if not (block.get("schedulable_reason") or "").strip():
        errors.append(f"{sid}: ensemble states no schedulable_reason")
    return errors


def ensemble_build_order_errors(data: dict[str, Any]) -> list[str]:
    """Six families, one declared order, and the registry constant agrees.

    The order is a registry fact so that a partial build is a prefix of the
    list rather than an implementation convention. That only holds if the
    ``build_order`` values are exactly 1 to 6 with no duplicate and no gap, and
    if reading them back gives the same sequence as
    ``source_data.ENSEMBLE_BUILD_ORDER``, which is what every other module
    reads.
    """
    errors: list[str] = []
    declared = {
        source["id"]: source["ensemble"]["build_order"]
        for source in data["sources"]
        if isinstance(source.get("ensemble"), dict) and "build_order" in source["ensemble"]
    }
    if sorted(declared.values()) != list(range(1, len(ENSEMBLE_BUILD_ORDER) + 1)):
        errors.append(
            f"ensemble build order values are {sorted(declared.values())}; the admitted families "
            f"take 1 to {len(ENSEMBLE_BUILD_ORDER)} exactly once each"
        )
    ordered = tuple(sorted(declared, key=lambda sid: (declared[sid], sid)))
    if ordered != tuple(ENSEMBLE_BUILD_ORDER):
        errors.append(
            f"ensemble build order reads {list(ordered)} and source_data.ENSEMBLE_BUILD_ORDER is "
            f"{list(ENSEMBLE_BUILD_ORDER)}; the declared order is one fact, not two"
        )
    return errors


def ensemble_errors(data: dict[str, Any]) -> list[str]:
    """Every refusal an ensemble declaration owes the rest of the stack."""
    errors: list[str] = []
    for source in data["sources"]:
        errors.extend(ensemble_presence_errors(source))
        block = source.get("ensemble")
        if not isinstance(block, dict):
            continue
        sid = source["id"]
        errors.extend(ensemble_scope_errors(sid, block))
        errors.extend(ensemble_shape_errors(sid, block))
        errors.extend(ensemble_gap_errors(sid, block))
        errors.extend(ensemble_verification_errors(sid, block))
    errors.extend(ensemble_build_order_errors(data))
    return errors


def state_errors(
    source: dict[str, Any],
    adapter_ids: set[str],
    known_ids: set[str] | None = None,
) -> list[str]:
    """Everything the declared state itself promises about the rest of the record.

    One state is refused outright: ``operational`` is the vocabulary's top and
    no source may claim it, so a record declaring it is an error rather than a
    record the ceiling quietly lowers. The rest are consistency checks. A
    record cannot claim to be implemented without an adapter, a passing fixture
    and a real integration; a terminal record cannot carry tests that will
    never run; a record with no data path cannot list one; and the two states
    that require a block (``credential-required``, ``superseded``) may not be
    declared without it, nor may the block appear without the state.
    """
    sid = source["id"]
    status = source["status"]
    errors: list[str] = []
    if status not in ALLOWED_STATUSES:
        errors.append(f"{sid}: invalid status {status!r}")
        return errors
    if status == "operational":
        errors.append(f"{sid}: declares operational, which no source may claim")
    if status == "implemented-unverified" and not admission.implemented_unverified_ok(source, adapter_ids):
        errors.append(
            f"{sid}: claims implemented-unverified with no registered adapter, "
            "a link_only integration or a fixture that is not passing"
        )
    if status in admission.TERMINAL_STATES:
        if source["fixture_status"] != "not_applicable" or source["live_smoke_test_status"] != "not_applicable":
            errors.append(f"{sid}: terminal status must mark fixture and live tests not_applicable")
    if status in admission.NO_ACCESS_PATH_STATES and source["access_endpoints"]:
        errors.append(f"{sid}: status {status!r} declares no data path, so access_endpoints must be empty")
    has_credential = source.get("credential") is not None
    if status == "credential-required" and not has_credential:
        errors.append(f"{sid}: credential-required needs a credential block")
    if has_credential and status != "credential-required":
        errors.append(f"{sid}: carries a credential block without status credential-required")
    successor = source.get("superseded_by")
    if status == "superseded" and successor is None:
        errors.append(f"{sid}: superseded must name its successor in superseded_by")
    if successor is not None:
        if status != "superseded":
            errors.append(f"{sid}: carries superseded_by without status superseded")
        if known_ids is not None and successor["source_id"] not in known_ids:
            errors.append(f"{sid}: superseded_by names unknown source id {successor['source_id']!r}")
    return errors


def credential_errors(source: dict[str, Any]) -> list[str]:
    """The credential block names a secret; it must never carry one.

    The schema already forbids any key but the name and the registration URL,
    which is what keeps key material out of the record. What is checked here is
    that the name is one ``ingest/secrets.py`` could map, and that the record's
    own ``authentication`` block agrees with it: a source that needs a
    credential says so in both places, and points at the same registration
    page from both.
    """
    block = source.get("credential")
    if block is None:
        return []
    sid = source["id"]
    errors: list[str] = []
    name = block["name"]
    if not _CREDENTIAL_NAME.match(name):
        errors.append(f"{sid}: credential name {name!r} is not a WEATHER_SECRET_* environment variable name")
    auth = source["authentication"]
    if not auth["required"]:
        errors.append(f"{sid}: credential-required must set authentication.required=true")
    if auth["registration_url"] != block["registration_url"]:
        errors.append(f"{sid}: authentication.registration_url must equal the credential block's registration_url")
    return errors


def restricted_terms_errors(source: dict[str, Any]) -> list[str]:
    """Research-use admission is recorded, not assumed.

    A record admitted under terms that forbid redistribution carries the clause
    verbatim, so a later reader can check the admission against the words
    rather than against someone's summary of them. Whitespace is not a clause.
    The rest of the record has to agree: the licence is under restriction, and
    the values may not stand as a centre's vote in a consensus.
    """
    block = source.get("restricted_terms")
    if block is None:
        return []
    sid = source["id"]
    errors: list[str] = []
    if not block["terms_text"].strip():
        errors.append(f"{sid}: restricted_terms needs the verbatim clause, not blank text")
    if source["licence"]["review_state"] != "restricted":
        errors.append(f"{sid}: restricted_terms requires licence.review_state 'restricted'")
    if source["consensus"]["eligible"]:
        errors.append(f"{sid}: a research-use-only source may not be consensus-eligible")
    return errors


def condition_errors(source: dict[str, Any]) -> list[str]:
    """An outstanding condition has to say what it is and what would end it.

    A condition nobody can act on is a permanent block dressed as a temporary
    one, so both halves are required to be real text.
    """
    block = source.get("admission_condition")
    if block is None:
        return []
    sid = source["id"]
    errors: list[str] = []
    if not block["condition"].strip():
        errors.append(f"{sid}: admission_condition needs a condition, not blank text")
    if not block["satisfied_by"].strip():
        errors.append(f"{sid}: admission_condition needs to say what would satisfy it")
    return errors


def no_endpoint_errors(source: dict[str, Any]) -> list[str]:
    """A source cited but never fetched has to look that way in both places.

    ``state_errors`` already refuses an endpoint on the three no-path states.
    What is added here is the other half for the two citation states: a
    ``link-only`` or ``partnership-only`` record whose integration still claims
    a typed adapter reads as a source something could fetch, and the next
    person to wire the worker would believe it. The integration kind has to say
    ``link_only`` too, so the declaration is unambiguous from either end.
    """
    status = source["status"]
    if status not in ("link-only", "partnership-only"):
        return []
    sid = source["id"]
    errors: list[str] = []
    if source["access_endpoints"]:
        errors.append(f"{sid}: status {status!r} may not carry an access endpoint")
    if source["integration"]["kind"] != "link_only":
        errors.append(f"{sid}: status {status!r} requires integration.kind 'link_only'")
    return errors


def export_errors(data: dict[str, Any]) -> list[str]:
    """No export path may carry the values of a research-use-only record.

    Decision 3 admits a restricted source on the promise that its values are
    served only to the owner's own reader. There are exactly two ways a value
    leaves a record in this registry: it is shown as the display primary, or it
    stands as a centre's vote in a consensus. Both are refused on a record
    carrying ``restricted_terms``, so the promise is checked here rather than
    remembered at each call site.
    """
    errors: list[str] = []
    for source in data["sources"]:
        if source.get("restricted_terms") is None:
            continue
        sid = source["id"]
        if source.get("display_primary"):
            errors.append(
                f"{sid}: research-use-only terms forbid an export path, so it may not be display_primary"
            )
        if source["consensus"]["eligible"]:
            errors.append(
                f"{sid}: research-use-only terms forbid an export path, so it may not be consensus-eligible"
            )
    return errors


#: The sentence the glossary entry opens with. The ten names follow it, comma
#: separated, and the entry's next sentence ends the list.
_GLOSSARY_LEAD = "The ceiling a source may reach:"

#: The one name the glossary and the registry spell differently. The glossary
#: called this state credential-blocked; the resolutions call it
#: credential-required and that name wins, because it says the source is
#: admitted rather than refused.
_GLOSSARY_ALIASES = {"credential-blocked": "credential-required"}


def glossary_state_errors(path: Path | None = None) -> list[str]:
    """The glossary and the schema enum name the same ten states.

    The glossary at the repo root is the domain model a reader consults; the
    enum is what the audit enforces. If they drift, one of them is lying and
    there is no way to tell which from inside either file, so they are compared
    here on every run. A missing glossary is an error rather than a skip: the
    check that silently passes when its input disappears is the check nobody
    notices has stopped working.
    """
    path = path or HERE.parents[2] / "CONTEXT.md"
    if not path.exists():
        return [f"glossary: {path} is missing, so the state list cannot be cross-checked"]
    text = path.read_text(encoding="utf-8")
    marker = text.find(_GLOSSARY_LEAD)
    if marker < 0:
        return [f"glossary: no 'Registry state' entry found in {path.name}"]
    start = marker + len(_GLOSSARY_LEAD)
    end = text.find(".", start)
    if end < 0:
        return [f"glossary: the 'Registry state' list in {path.name} does not end in a sentence"]
    listed = {
        _GLOSSARY_ALIASES.get(name, name)
        for name in (part.strip() for part in text[start:end].replace("\n", " ").split(","))
        if name
    }
    expected = set(admission.STATES)
    errors: list[str] = []
    missing = sorted(expected - listed)
    if missing:
        errors.append(f"glossary: 'Registry state' omits {', '.join(missing)}")
    extra = sorted(listed - expected)
    if extra:
        errors.append(f"glossary: 'Registry state' names states the schema does not have: {', '.join(extra)}")
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

    adapter_ids = adapter_source_ids()

    for source in sources:
        sid = source["id"]
        auth = source["authentication"]
        errors.extend(state_errors(source, adapter_ids, known))
        errors.extend(credential_errors(source))
        errors.extend(restricted_terms_errors(source))
        errors.extend(condition_errors(source))
        errors.extend(no_endpoint_errors(source))
        if auth["required"] and not auth["registration_url"]:
            errors.append(f"{sid}: authenticated source needs an official registration URL")
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
    errors.extend(ensemble_errors(data))
    return errors


def validate(data: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    data = data or registry()
    schema = load_json(HERE / "schema.json")
    coverage = load_json(HERE / "catalogue_coverage.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = [f"schema {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}" for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))]
    errors.extend(semantic_errors(data, coverage))
    errors.extend(export_errors(data))
    errors.extend(glossary_state_errors())
    errors.extend(catalogue_errors())
    return data, errors


def summary(data: dict[str, Any]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    categories: dict[str, int] = {}
    delivery_kinds: dict[str, int] = {}
    adapter_ids = adapter_source_ids()
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
        "adapter_source_ids": sorted(adapter_ids),
        # The admission ledger, in the shape a reader can check against the
        # design. Lists rather than counts wherever naming the records is the
        # point: which declarations the worker may fetch, which are held back
        # by a condition nobody has closed, and which carry terms that keep
        # their values off every export path.
        "ceiling": {state: admission.ceiling_state(state) for state in admission.STATES},
        "schedulable_by_registry": sorted(
            source["id"] for source in data["sources"]
            if admission.declaration_schedulable(source, adapter_ids)
        ),
        "admission_conditions_outstanding": sorted(
            source["id"] for source in data["sources"] if admission.condition_outstanding(source)
        ),
        "research_use_only": sorted(
            source["id"] for source in data["sources"] if source.get("restricted_terms") is not None
        ),
        "credential_required": sorted(
            source["id"] for source in data["sources"] if source["status"] == "credential-required"
        ),
        "no_access_path": sorted(
            source["id"] for source in data["sources"] if not source["access_endpoints"]
        ),
        # The two halves of the Decision 1 split, so that a run can be compared
        # against the 21/29 the migration was expected to produce.
        "migration_split": {
            "implemented-unverified": statuses.get("implemented-unverified", 0),
            "catalogued": statuses.get("catalogued", 0),
        },
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
        split = report["migration_split"]
        print(
            f"admission: {split['implemented-unverified']} implemented-unverified, "
            f"{split['catalogued']} catalogued, "
            f"{len(report['schedulable_by_registry'])} schedulable by the registry "
            f"({len(report['admission_conditions_outstanding'])} held by an outstanding condition, "
            f"{len(report['research_use_only'])} research use only, "
            f"{len(report['credential_required'])} credential-required, "
            f"{len(report['no_access_path'])} with no access path)"
        )
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
