#!/usr/bin/env python3
"""Validate and scaffold Astraeus specifications."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi


ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = ROOT / "docs" / "specv1"
TEMPLATE_ROOT = SPEC_ROOT / "_templates"
REQUIREMENT_INDEX = SPEC_ROOT / "REQUIREMENTS.json"
MODULE_REGISTRY = SPEC_ROOT / "contracts" / "observation-modules.yaml"
MODULE_REGISTRY_SCHEMA = (
    SPEC_ROOT / "contracts" / "schemas" / "observation-module-registry.schema.json"
)

ALLOWED_STATUSES = {
    "draft",
    "proposed",
    "accepted",
    "implemented",
    "verified",
    "superseded",
}
ALLOWED_TYPES = {
    "index",
    "governance",
    "reference",
    "prd",
    "rfc",
    "adr",
    "feature-index",
    "feature",
    "science-spec",
    "data-spec",
    "safety-spec",
    "ux-spec",
    "delivery-spec",
    "verification",
    "contract-index",
    "rule-index",
}
REGISTERED_PREFIXES = {"GOV", "PRD", "SYS", "EVD", "MAP", "OPS", "SITE", "ECL26"}
PREFIX_PATTERN = "|".join(re.escape(prefix) for prefix in sorted(REGISTERED_PREFIXES))
REQUIRED_FRONTMATTER = {
    "id",
    "title",
    "type",
    "status",
    "owners",
    "profiles",
    "created",
    "updated",
    "depends_on",
    "supersedes",
}
REQUIREMENT_RE = re.compile(
    rf"^#{{2,6}}\s+((?:{PREFIX_PATTERN})-[A-Z0-9]+-\d{{3}})\s+—\s+(.+?)\s*$"
)
TEST_RE = re.compile(
    rf"\b((?:{PREFIX_PATTERN})-[A-Z0-9]+-\d{{3}}-T\d{{2}})\b"
)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|spec|refactor|test|perf|build|ci|chore)"
    r"\([a-z0-9][a-z0-9-]*\): [a-z0-9].{2,71}$"
)
BEHAVIOR_PATH_PREFIXES = (
    "apps/",
    "services/",
    "packages/contracts/",
    "packages/domain/",
    "packages/api-client/",
    "packages/ui-web/",
    "packages/ui-mobile/",
    "infra/",
    "docs/specv1/",
)


@dataclass(frozen=True)
class Document:
    path: Path
    metadata: dict[str, Any]
    body: str
    requirements: dict[str, str]
    tests: set[str]

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def report(self) -> int:
        for warning in sorted(self.warnings):
            print(f"WARNING: {warning}", file=sys.stderr)
        for error in sorted(self.errors):
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"specctl: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return 1 if self.errors else 0


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        _, raw_metadata, body = text.split("---\n", 2)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc
    metadata = yaml.safe_load(raw_metadata)
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return metadata, body


def markdown_slug(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value)
    return value.strip("-")


def collect_documents(validation: Validation) -> list[Document]:
    documents: list[Document] = []
    for path in sorted(SPEC_ROOT.rglob("*.md")):
        if TEMPLATE_ROOT in path.parents:
            continue
        try:
            metadata, body = parse_frontmatter(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            validation.error(f"{path.relative_to(ROOT)}: {exc}")
            continue

        missing = REQUIRED_FRONTMATTER - metadata.keys()
        if missing:
            validation.error(
                f"{path.relative_to(ROOT)}: missing frontmatter {sorted(missing)}"
            )
        status = metadata.get("status")
        if status not in ALLOWED_STATUSES:
            validation.error(f"{path.relative_to(ROOT)}: invalid status {status!r}")
        doc_type = metadata.get("type")
        if doc_type not in ALLOWED_TYPES:
            validation.error(f"{path.relative_to(ROOT)}: invalid type {doc_type!r}")
        owners = metadata.get("owners")
        if not isinstance(owners, list) or not owners:
            validation.error(f"{path.relative_to(ROOT)}: owners must be non-empty")
        if status in {"accepted", "verified", "superseded"} and "@TusharSariya" not in (
            owners or []
        ):
            validation.error(
                f"{path.relative_to(ROOT)}: normative status requires @TusharSariya owner"
            )
        if status in {"accepted", "implemented", "verified"}:
            unresolved = re.search(r"\b(TODO|TBD|FIXME)\b", body)
            if unresolved:
                validation.error(
                    f"{path.relative_to(ROOT)}: {status} document contains {unresolved.group(1)}"
                )

        line_count = path.read_text(encoding="utf-8").count("\n") + 1
        if line_count > 1000 and not metadata.get("size_exemption"):
            validation.error(
                f"{path.relative_to(ROOT)}: {line_count} lines exceeds 1000 without size_exemption"
            )
        elif line_count > 500:
            validation.warn(f"{path.relative_to(ROOT)}: {line_count} lines; consider splitting")

        requirements: dict[str, str] = {}
        for line in body.splitlines():
            match = REQUIREMENT_RE.match(line)
            if match:
                requirements[match.group(1)] = match.group(2)
        tests = set(TEST_RE.findall(body))
        documents.append(Document(path, metadata, body, requirements, tests))
    return documents


def validate_documents(validation: Validation, documents: list[Document]) -> None:
    doc_ids: dict[str, Document] = {}
    requirements: dict[str, Document] = {}
    tests: dict[str, Document] = {}

    for document in documents:
        doc_id = str(document.metadata.get("id", ""))
        if not doc_id:
            continue
        if doc_id in doc_ids:
            validation.error(
                f"duplicate document id {doc_id}: {doc_ids[doc_id].relative_path}, {document.relative_path}"
            )
        doc_ids[doc_id] = document
        for requirement_id in document.requirements:
            prefix = requirement_id.split("-", 1)[0]
            if prefix not in REGISTERED_PREFIXES:
                validation.error(
                    f"{document.relative_path}: unregistered prefix in {requirement_id}"
                )
            if requirement_id in requirements:
                validation.error(
                    f"duplicate requirement {requirement_id}: "
                    f"{requirements[requirement_id].relative_path}, {document.relative_path}"
                )
            requirements[requirement_id] = document
        for test_id in document.tests:
            if test_id in tests and tests[test_id].path != document.path:
                validation.error(
                    f"duplicate verification id {test_id}: "
                    f"{tests[test_id].relative_path}, {document.relative_path}"
                )
            tests[test_id] = document

    known_ids = set(doc_ids) | set(requirements)
    status_by_id = {doc_id: doc.metadata.get("status") for doc_id, doc in doc_ids.items()}
    status_by_id.update(
        {
            requirement_id: document.metadata.get("status")
            for requirement_id, document in requirements.items()
        }
    )
    dependency_graph: dict[str, list[str]] = {}
    for document in documents:
        dependencies = document.metadata.get("depends_on", []) or []
        supersedes = document.metadata.get("supersedes", []) or []
        if not isinstance(dependencies, list) or not isinstance(supersedes, list):
            validation.error(
                f"{document.relative_path}: depends_on and supersedes must be arrays"
            )
            continue
        for referenced_id in dependencies + supersedes:
            if referenced_id not in known_ids:
                validation.error(
                    f"{document.relative_path}: unknown dependency/supersession {referenced_id}"
                )
        if document.metadata.get("status") in {"accepted", "implemented", "verified"}:
            for referenced_id in dependencies:
                dependency_status = status_by_id.get(referenced_id)
                if dependency_status not in {"accepted", "implemented", "verified"}:
                    validation.error(
                        f"{document.relative_path}: normative document depends on "
                        f"{dependency_status} {referenced_id}"
                    )
        dependency_graph[str(document.metadata.get("id"))] = [
            item for item in dependencies if item in doc_ids
        ]

        for link in LINK_RE.findall(document.body):
            raw_target, _, fragment = link.partition("#")
            target = raw_target.split("?", 1)[0]
            if not target or re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
                continue
            resolved = (document.path.parent / target).resolve()
            if ROOT not in resolved.parents and resolved != ROOT:
                validation.error(f"{document.relative_path}: link escapes repository: {link}")
            elif not resolved.exists():
                validation.error(f"{document.relative_path}: broken internal link {link}")
            elif fragment and resolved.suffix.lower() == ".md":
                target_text = resolved.read_text(encoding="utf-8")
                anchors = {
                    markdown_slug(line.lstrip("#").strip())
                    for line in target_text.splitlines()
                    if re.match(r"^#{1,6}\s+", line)
                }
                if fragment not in anchors:
                    validation.error(
                        f"{document.relative_path}: unknown anchor #{fragment} in {target}"
                    )

    _validate_dependency_cycles(validation, dependency_graph)

    for test_id, document in tests.items():
        requirement_id = test_id.rsplit("-T", 1)[0]
        if requirement_id not in requirements:
            validation.error(
                f"{document.relative_path}: verification {test_id} references unknown {requirement_id}"
            )

    verified_requirements = {test_id.rsplit("-T", 1)[0] for test_id in tests}
    for requirement_id, document in requirements.items():
        if document.metadata.get("status") in {"implemented", "verified"}:
            if requirement_id not in verified_requirements:
                validation.error(
                    f"{document.relative_path}: {requirement_id} lacks mapped verification"
                )


def _validate_dependency_cycles(
    validation: Validation, graph: dict[str, list[str]]
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            start = trail.index(node)
            validation.error(
                "document dependency cycle: " + " -> ".join(trail[start:] + [node])
            )
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency, trail + [dependency])
        visiting.remove(node)
        visited.add(node)

    for document_id in graph:
        visit(document_id, [document_id])


def validate_contracts(
    validation: Validation, documents: list[Document]
) -> None:
    for path in sorted((SPEC_ROOT / "contracts" / "schemas").glob("*.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # library exposes several validation subclasses
            validation.error(f"{path.relative_to(ROOT)}: invalid JSON Schema: {exc}")

    openapi_path = SPEC_ROOT / "contracts" / "openapi.yaml"
    openapi_document: dict[str, Any] = {}
    try:
        value = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("OpenAPI root must be a mapping")
        openapi_document = value
        validate_openapi(openapi_document)
    except Exception as exc:
        validation.error(f"{openapi_path.relative_to(ROOT)}: invalid OpenAPI: {exc}")

    validate_module_registry(validation, documents, openapi_document)

    for path in sorted((SPEC_ROOT / "rules").glob("*.yaml")):
        try:
            rule = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            validation.error(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")
            continue
        if not isinstance(rule, dict):
            validation.error(f"{path.relative_to(ROOT)}: rule file must be a mapping")
            continue
        for field in ("rule_set_id", "version", "status", "owner", "approval"):
            if field not in rule:
                validation.error(f"{path.relative_to(ROOT)}: missing {field}")
        if rule.get("status") not in {"draft", "accepted", "superseded"}:
            validation.error(f"{path.relative_to(ROOT)}: invalid rule status")
        if rule.get("status") == "accepted":
            approval = rule.get("approval") or {}
            if approval.get("accepted_by") != "@TusharSariya" or not approval.get(
                "accepted_at"
            ):
                validation.error(
                    f"{path.relative_to(ROOT)}: accepted rule lacks owner approval"
                )
            if _contains_null_threshold(rule):
                validation.error(
                    f"{path.relative_to(ROOT)}: accepted rule contains null threshold"
                )


def validate_module_registry_data(
    validation: Validation,
    registry: Any,
    schema: dict[str, Any],
) -> bool:
    starting_error_count = len(validation.errors)
    if not isinstance(registry, dict):
        validation.error(
            "docs/specv1/contracts/observation-modules.yaml: registry must be a mapping"
        )
        return False

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(registry), key=lambda error: list(error.path))
    for error in errors:
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        validation.error(
            "docs/specv1/contracts/observation-modules.yaml: "
            f"{location}: {error.message}"
        )

    seen_versions: set[tuple[str, str]] = set()
    active_majors: set[tuple[str, str]] = set()
    for module in registry.get("modules", []):
        if not isinstance(module, dict):
            continue
        module_id = module.get("module_id")
        version = module.get("version")
        if not isinstance(module_id, str) or not isinstance(version, str):
            continue
        identity = (module_id, version)
        if identity in seen_versions:
            validation.error(
                "docs/specv1/contracts/observation-modules.yaml: duplicate module "
                f"identity {module_id}@{version}"
            )
        seen_versions.add(identity)
        major = version.split(".", 1)[0]
        active_identity = (module_id, major)
        if module.get("status") == "active":
            if active_identity in active_majors:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: multiple active "
                    f"{module_id} major version {major} entries"
                )
            active_majors.add(active_identity)
    return not errors and len(validation.errors) == starting_error_count


def validate_module_registry(
    validation: Validation,
    documents: list[Document],
    openapi_document: dict[str, Any],
) -> None:
    try:
        schema = json.loads(MODULE_REGISTRY_SCHEMA.read_text(encoding="utf-8"))
        registry = yaml.safe_load(MODULE_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        validation.error(
            "docs/specv1/contracts/observation-modules.yaml: "
            f"unable to load registry/schema: {exc}"
        )
        return

    if not validate_module_registry_data(validation, registry, schema):
        return

    known_tests = {test for document in documents for test in document.tests}
    document_status = {
        str(document.metadata.get("id")): document.metadata.get("status")
        for document in documents
    }
    components = openapi_document.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    if not isinstance(schemas, dict):
        schemas = {}
    contract_root = MODULE_REGISTRY.parent
    for module in registry["modules"]:
        identity = f"{module['module_id']}@{module['version']}"
        for field in ("request_schema", "result_schema"):
            reference = module[field]
            prefix = "openapi.yaml#/components/schemas/"
            if not reference.startswith(prefix) or reference.removeprefix(prefix) not in schemas:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: "
                    f"{identity} has unresolved {field} {reference!r}"
                )

        resolved_paths: dict[str, Path] = {}
        for field in ("science_spec", "safety_spec", "scoring_rule"):
            resolved = (contract_root / module[field]).resolve()
            resolved_paths[field] = resolved
            if ROOT not in resolved.parents or not resolved.exists():
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: "
                    f"{identity} has unresolved {field} {module[field]!r}"
                )

        for test_id in module["verification_refs"]:
            if test_id not in known_tests:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: "
                    f"{identity} references unknown verification {test_id}"
                )

        if module["status"] != "active":
            continue
        if "-" in module["version"]:
            validation.error(
                "docs/specv1/contracts/observation-modules.yaml: active "
                f"{identity} cannot use a prerelease version"
            )
        for owning_document in ("RFC-005", "SPECV1-CONTRACTS"):
            if document_status.get(owning_document) not in {
                "accepted",
                "implemented",
                "verified",
            }:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: active "
                    f"{identity} depends on {document_status.get(owning_document)} "
                    f"{owning_document}"
                )
        for field in ("science_spec", "safety_spec"):
            path = resolved_paths[field]
            if not path.exists():
                continue
            try:
                metadata, _ = parse_frontmatter(path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: active "
                    f"{identity} cannot read {field}: {exc}"
                )
                continue
            if metadata.get("status") not in {"accepted", "implemented", "verified"}:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: active "
                    f"{identity} depends on {metadata.get('status')} {field}"
                )
        rule_path = resolved_paths["scoring_rule"]
        if rule_path.exists():
            try:
                rule = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: active "
                    f"{identity} cannot read scoring_rule: {exc}"
                )
                continue
            if not isinstance(rule, dict) or rule.get("status") != "accepted":
                validation.error(
                    "docs/specv1/contracts/observation-modules.yaml: active "
                    f"{identity} requires an accepted scoring rule"
                )


def _contains_null_threshold(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "threshold" and child is None) or _contains_null_threshold(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_null_threshold(child) for child in value)
    return False


def build_index(documents: list[Document]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for document in documents:
        for requirement_id, title in document.requirements.items():
            entries.append(
                {
                    "id": requirement_id,
                    "title": title,
                    "document_id": document.metadata["id"],
                    "status": document.metadata["status"],
                    "path": document.relative_path,
                    "anchor": markdown_slug(f"{requirement_id} — {title}"),
                    "profiles": document.metadata.get("profiles", []),
                }
            )
    return {"schema_version": 1, "requirements": sorted(entries, key=lambda x: x["id"])}


def index_text(index: dict[str, Any]) -> str:
    return json.dumps(index, indent=2, sort_keys=True) + "\n"


def validate_index(validation: Validation, documents: list[Document]) -> None:
    expected = index_text(build_index(documents))
    if not REQUIREMENT_INDEX.exists():
        validation.error("docs/specv1/REQUIREMENTS.json is missing; run specctl index --write")
    elif REQUIREMENT_INDEX.read_text(encoding="utf-8") != expected:
        validation.error("docs/specv1/REQUIREMENTS.json is stale; run specctl index --write")


def changed_files(base: str, head: str) -> list[str]:
    base_sha = resolve_commit(base)
    head_sha = resolve_commit(head)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_sha}...{head_sha}", "--"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"unable to diff revisions: {exc.stderr.strip()}") from exc
    return [line for line in result.stdout.splitlines() if line]


def resolve_commit(revision: str) -> str:
    if not revision or revision.startswith("-"):
        raise ValueError(f"invalid revision {revision!r}")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"unresolvable revision {revision!r}") from exc
    sha = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"revision did not resolve to a commit SHA: {revision!r}")
    return sha


def behavior_changing(paths: Iterable[str]) -> bool:
    return any(path.startswith(BEHAVIOR_PATH_PREFIXES) for path in paths)


def validate_pr_payload(
    validation: Validation,
    payload: dict[str, Any],
    known_requirements: dict[str, dict[str, Any]],
    changed: list[str],
    protected_status_changes: list[str] | None = None,
) -> None:
    pull_request = payload.get("pull_request", {})
    title = pull_request.get("title", "")
    body = pull_request.get("body") or ""
    visible_body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    labels = {item.get("name") for item in pull_request.get("labels", [])}

    if not CONVENTIONAL_RE.fullmatch(title):
        validation.error(
            "PR title must be conventional: <type>(<scope>): <imperative summary>"
        )
    match = re.search(r"^Spec-Refs:\s*(.+)$", visible_body, re.MULTILINE)
    no_impact = re.search(r"^Spec-Impact:\s*none\s*$", visible_body, re.MULTILINE)

    if behavior_changing(changed) and not match:
        validation.error("behavior-changing PR requires Spec-Refs")
    if not behavior_changing(changed) and not match and not no_impact:
        validation.error("PR requires Spec-Refs or Spec-Impact: none")
    if no_impact and not re.search(
        r"^No-Spec-Impact-Rationale:\s*\S.+$", visible_body, re.MULTILINE
    ):
        validation.error("Spec-Impact: none requires No-Spec-Impact-Rationale")
    if match:
        refs = [item.strip() for item in match.group(1).split(",") if item.strip()]
        for ref in refs:
            entry = known_requirements.get(ref)
            if entry is None:
                validation.error(f"PR references unknown requirement {ref}")
            elif entry["status"] not in {"accepted", "implemented", "verified"}:
                validation.error(
                    f"PR references {entry['status']} requirement {ref}; production work requires accepted"
                )
            if not re.search(rf"\[{re.escape(ref)}\]\([^)]+\)", visible_body):
                validation.error(f"PR must include a clickable link for {ref}")
        if not re.search(r"^Verification:\s*\S.+$", visible_body, re.MULTILINE):
            validation.error("PR with Spec-Refs requires Verification")

    if protected_status_changes and "spec-status-approved" not in labels:
        validation.error(
            "accepted/verified/superseded status transition requires "
            "the owner-controlled spec-status-approved label"
        )


def detect_protected_status_changes(base: str, head: str) -> list[str]:
    changed: list[str] = []
    for path in changed_files(base, head):
        if not path.startswith("docs/specv1/") or not path.endswith(".md"):
            continue
        before = _git_frontmatter(base, path)
        after = _git_frontmatter(head, path)
        before_status = before.get("status") if before else None
        after_status = after.get("status") if after else None
        if after_status in {"accepted", "verified", "superseded"} and after_status != before_status:
            changed.append(path)
    return changed


def _git_frontmatter(revision: str, path: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout.startswith("---\n"):
        return {}
    try:
        _, raw, _ = result.stdout.split("---\n", 2)
        value = yaml.safe_load(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, yaml.YAMLError):
        return {}


def command_validate(_: argparse.Namespace) -> int:
    validation = Validation()
    documents = collect_documents(validation)
    validate_documents(validation, documents)
    validate_contracts(validation, documents)
    validate_index(validation, documents)
    return validation.report()


def command_index(args: argparse.Namespace) -> int:
    validation = Validation()
    documents = collect_documents(validation)
    validate_documents(validation, documents)
    content = index_text(build_index(documents))
    if args.write:
        REQUIREMENT_INDEX.write_text(content, encoding="utf-8")
        print(REQUIREMENT_INDEX.relative_to(ROOT))
    elif not REQUIREMENT_INDEX.exists() or REQUIREMENT_INDEX.read_text(encoding="utf-8") != content:
        validation.error("requirements index is stale; use --write")
    return validation.report()


def command_resolve(args: argparse.Namespace) -> int:
    if not REQUIREMENT_INDEX.exists():
        print("requirements index missing; run specctl index --write", file=sys.stderr)
        return 1
    index = json.loads(REQUIREMENT_INDEX.read_text(encoding="utf-8"))
    for entry in index["requirements"]:
        if entry["id"] == args.requirement_id:
            print(f"{entry['path']}#{entry['anchor']}")
            return 0
    print(f"unknown requirement: {args.requirement_id}", file=sys.stderr)
    return 1


def command_changed(args: argparse.Namespace) -> int:
    try:
        paths = changed_files(args.base, args.head)
    except ValueError as exc:
        print(f"specctl: {exc}", file=sys.stderr)
        return 2
    result = {"behavior_changing": behavior_changing(paths), "paths": paths}
    print(json.dumps(result, indent=2))
    return 0


def command_validate_pr(args: argparse.Namespace) -> int:
    validation = Validation()
    documents = collect_documents(validation)
    index = build_index(documents)
    known = {entry["id"]: entry for entry in index["requirements"]}
    payload = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request", {})
    base = pull_request.get("base", {}).get("sha")
    head = pull_request.get("head", {}).get("sha")
    paths: list[str] = []
    protected_status_changes: list[str] = []
    if not base or not head:
        validation.error("pull request event is missing base.sha or head.sha")
    elif not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(
        r"[0-9a-f]{40}", head
    ):
        validation.error("pull request base.sha and head.sha must be full commit SHAs")
    else:
        try:
            paths = changed_files(base, head)
            protected_status_changes = detect_protected_status_changes(base, head)
        except ValueError as exc:
            validation.error(str(exc))
    validate_pr_payload(
        validation, payload, known, paths, protected_status_changes
    )
    return validation.report()


def command_new(args: argparse.Namespace) -> int:
    today = date.today().isoformat()
    if args.kind == "feature":
        slug = args.name.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            print("feature slug must be lower-case hyphen form", file=sys.stderr)
            return 2
        if not args.prefix or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", args.prefix):
            print("feature requires --prefix with 3-10 upper-case letters/digits", file=sys.stderr)
            return 2
        target = SPEC_ROOT / "features" / slug
        if target.exists():
            print(f"target exists: {target.relative_to(ROOT)}", file=sys.stderr)
            return 1
        shutil.copytree(TEMPLATE_ROOT / "feature", target)
        for path in target.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            text = text.replace("FEATURE", args.prefix).replace("PREFIX", args.prefix)
            text = text.replace("Replace me", slug.replace("-", " ").title())
            text = text.replace("YYYY-MM-DD", today)
            path.write_text(text, encoding="utf-8")
        print(target.relative_to(ROOT))
        return 0

    number = args.number
    if number is None:
        print(f"{args.kind} requires --number", file=sys.stderr)
        return 2
    kind = args.kind.upper()
    template = TEMPLATE_ROOT / f"{kind}.md"
    slug = markdown_slug(args.name).upper()
    target_dir = SPEC_ROOT / ("rfcs" if args.kind == "rfc" else "adrs")
    target = target_dir / f"{kind}-{number:03d}-{slug}.md"
    if target.exists():
        print(f"target exists: {target.relative_to(ROOT)}", file=sys.stderr)
        return 1
    text = template.read_text(encoding="utf-8")
    text = text.replace(f"{kind}-NNN", f"{kind}-{number:03d}")
    text = text.replace("Replace me", args.name).replace("YYYY-MM-DD", today)
    target.write_text(text, encoding="utf-8")
    print(target.relative_to(ROOT))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.set_defaults(func=command_validate)

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--write", action="store_true")
    index_parser.set_defaults(func=command_index)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("requirement_id")
    resolve_parser.set_defaults(func=command_resolve)

    changed_parser = subparsers.add_parser("changed")
    changed_parser.add_argument("--base", required=True)
    changed_parser.add_argument("--head", required=True)
    changed_parser.set_defaults(func=command_changed)

    pr_parser = subparsers.add_parser("validate-pr")
    pr_parser.add_argument("event_json")
    pr_parser.set_defaults(func=command_validate_pr)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("kind", choices=["feature", "rfc", "adr"])
    new_parser.add_argument("name")
    new_parser.add_argument("--prefix")
    new_parser.add_argument("--number", type=int)
    new_parser.set_defaults(func=command_new)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
