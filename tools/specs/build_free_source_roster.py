#!/usr/bin/env python3
"""Build and validate the issue 71 source implementation roster."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/research/unimplemented-sources-registry.json"
OUTPUT = ROOT / "docs/research/free-source-implementation-roster.json"
CHILD_TICKETS = ROOT / "docs/research/free-source-roster-child-tickets.json"

FROZEN_INPUT_HASHES = {
    "docs/research/unimplemented-sources-registry.json": "a03efc1462c95e0be12686dae9768231ea7ff23c7f7e0eee4af2a2f826c1281d",
    "docs/research/unimplemented-sources-ai-commercial.md": "842141d71dc9abe20839a08dd36d1fc4d7f2fb9b27b767240ca787f5a35b9800",
    "docs/research/unimplemented-sources-environmental.md": "fd8564459eba73f07d49b335ba533345ac7265b123460596ddb25c4d4fbfa8b7",
    "docs/research/unimplemented-sources-geospatial-celestial.md": "ecd7c05b79ce0733f899f82aad79b9fd09ed142e8f8a0cc691c0b6a015ed3397",
}

TASKS = {
    71: "Reconcile every audited source with the free-provider implementation roster",
    77: "Implement the verified WeatherNext forecast source",
    78: "Implement named Open-Meteo and Bright Sky source retrieval",
    79: "Implement deterministic GeoMet WCS fields and WEonG diagnostics",
    80: "Implement ECCC air-quality, precipitation and land analyses",
    81: "Complete native IFS, ICON, AIFS Single, RAP and NAM acquisition",
    82: "Complete ECMWF ensemble discovery and bounded retrieval",
    83: "Complete REPS and GEPS provider-product acquisition",
    84: "Complete GEFS and decide the free ICON ensemble path",
    85: "Implement the remaining free cloud and atmospheric satellite products",
    86: "Implement free aerosol, radiation and fire observations",
    87: "Implement free marine, ocean, ice and hydrometric evidence",
    88: "Implement additional free local and aviation observations",
    89: "Implement missing free space-weather measurements and forecasts",
    90: "Implement permissioned free camera and transport acquisition",
    91: "Implement free terrain, light-pollution and site-evidence acquisition",
    92: "Implement free orbital and celestial catalogue acquisitions",
    94: "Implement the selected free historical acquisition windows",
    95: "Prototype FourCastNet on available local compute",
    96: "Implement eligible free published AI forecast products",
    97: "Verify complete source coverage and hand off integrated evidence",
}

EXACT_TASK = {
    "eccc-hrdps-weg-prognos": 79,
    "eccc-reps": 83,
    "eccc-geps": 83,
    "ecmwf-ifs": 81,
    "ecmwf-ens": 82,
    "ecmwf-aifs-single": 81,
    "ecmwf-aifs-ens": 82,
    "noaa-gefs": 84,
    "dwd-icon-global": 81,
    "dwd-icon-eps": 84,
    "google-weathernext-2": 77,
    "open-meteo-weathernext-2": 77,
    "noaa-rap": 81,
    "noaa-nam": 81,
    "falchi-night-sky-atlas": 91,
    "viirs-dnb-night-lights": 91,
    "globe-at-night": 91,
    "nasa-jpl-de442": 97,
    "celestrak-gp": 92,
    "space-track": 92,
    "ccg-navwarn": 87,
    "eccc-swob": 97,
    "eccc-radar": 97,
    "eccc-lightning": 97,
    "eccc-cap-alerts": 97,
    "noaa-gfs": 97,
    "nasa-jpl-de442": 97,
}

PREFIX_TASK = {
    "openmeteo-": 78,
    "brightsky-": 78,
}

CATEGORY_TASK = {
    "ocean": 87,
    "wave": 87,
    "surge": 87,
    "marine": 87,
    "marine_observation": 87,
    "local_buoy": 87,
    "tide_water_level": 87,
    "hydrology": 87,
    "space_weather": 89,
    "camera": 90,
    "transport": 90,
    "aviation": 88,
    "optional_observation": 88,
    "optional_air_quality": 88,
    "air_quality": 86,
    "terrain": 91,
    "astronomy": 92,
    "satellite": 85,
}

TASK80_IDS = {
    "eccc-integrated-nowcasting", "eccc-hrdpa", "eccc-rdpa", "eccc-hrepa",
    "eccc-hrdlps", "eccc-caldas", "eccc-raqdps", "eccc-rdaqa",
    "eccc-wildfire-hotspots", "eccc-raqdps-firework",
    "eccc-thunderstorm-outlooks", "eccc-hurricane-products",
}

SUPPLEMENTAL_RESEARCH_ROWS = [
    # Explicit candidates in narrative prose rather than appendix tables.
    ("rrfs-na-conditional", "NOAA RRFS-NA conditional future covering feed", "docs/research/unimplemented-sources-ai-commercial.md:63", "recorded-conditional", 81),
    ("ukmo-global-ensemble", "UKMO Global ensemble distinct from deterministic Open-Meteo delivery", "docs/research/unimplemented-sources-ai-commercial.md:65", "recorded-unavailable-probe", 97),
    ("met-norway-products", "MET Norway Locationforecast and seamless products", "docs/research/unimplemented-sources-ai-commercial.md:67", "free-in-scope-coverage-check", 81),
    ("long-horizon-models", "SEAS5, EC46 and CanSIPS longer-horizon products", "docs/research/unimplemented-sources-ai-commercial.md:67", "outside-current-horizon", 97),
    ("regional-model-exclusions", "HRRR, NBM, AROME, MEPS, Nordic, Icelandic, Greenlandic and Iberian regional systems", "docs/research/unimplemented-sources-ai-commercial.md:67", "out-of-geography-or-unproved", 97),
    ("russian-products-underspecified", "Underspecified Russian forecast products", "docs/research/unimplemented-sources-ai-commercial.md:67", "insufficient-product-identity", 97),
    ("space-weather-research-only-group", "RTSW ephemerides, Geospace Dst, SWPC text/outlook, direct Kyoto/GFZ indices, NRCan Atom, GOES metadata, CCOR1, ACE fallback and SuperMAG", "docs/research/unimplemented-sources-environmental.md:119", "free-in-scope-or-permission-check", 89),
    ("space-weather-blocked-group", "STJ magnetometer, regional/solar imagery links, stale relays, irrelevant AuroraWatch sector and unavailable Aurorasaurus endpoint", "docs/research/unimplemented-sources-environmental.md:121", "recorded-blocked-or-excluded", 97),
    ("camera-research-only-group", "CBC harbour, The Rooms, Windy/Webcams.travel, MUN, Marine Institute, Parks Canada and Port camera leads", "docs/research/unimplemented-sources-environmental.md:125", "recorded-permission-or-no-feed", 90),
    ("gedi-canopy", "GEDI canopy product", "docs/research/unimplemented-sources-geospatial-celestial.md:56", "unsuitable-primary-local-source", 97),
    ("streetview-3d-tiles", "Google Street View and Photorealistic 3D Tiles", "docs/research/unimplemented-sources-geospatial-celestial.md:57", "no-unrestricted-automated-right", 97),
    ("illumina-tool", "Illumina offline sky-brightness modelling tool", "docs/research/unimplemented-sources-geospatial-celestial.md:58", "tool-or-method", 91),
    ("de440-de441-alternatives", "DE440 and DE441 historical ephemeris alternatives to selected DE442", "docs/research/unimplemented-sources-geospatial-celestial.md:91", "superseded-alternatives", 97),
    ("astronomy-software-toolkits", "Skyfield, Astropy, SGP4 and SPICE software toolkits", "docs/research/unimplemented-sources-geospatial-celestial.md:92", "tools-not-sources", 97),
]

EXTERNAL_BLOCK_STATES = {
    "credential-required", "licence-blocked", "partnership-only", "link-only",
    "unavailable", "rejected", "superseded",
}


def target_for(row: dict) -> int:
    source_id = row["source_id"]
    if source_id in EXACT_TASK:
        return EXACT_TASK[source_id]
    if source_id in TASK80_IDS:
        return 80
    for prefix, task in PREFIX_TASK.items():
        if source_id.startswith(prefix):
            return task
    if source_id.startswith("eccc-") and row["category"] in {
        "deterministic_forecast", "postprocessed_forecast", "humidity_profile"
    }:
        return 79
    return CATEGORY_TASK.get(row["category"], 97)


def access_for(row: dict, record: dict) -> tuple[str, str]:
    state = row["registry_status"]
    source_id = row["source_id"]
    if source_id == "meteosource":
        return "paid-or-commercial", "out-of-scope-paid"
    if state == "credential-required":
        return "free-account-or-permission-unverified", "externally-blocked"
    if state == "partnership-only":
        return "permission-required-no-public-endpoint", "externally-blocked"
    if state == "link-only":
        return "citation-only-no-retrieval-right", "recorded-disposition"
    if state in {"unavailable", "rejected", "superseded"}:
        return "no-eligible-current-path", "recorded-disposition"
    if record["authentication"]["required"]:
        return "account-or-key-required", "conditionally-free-pending-access-and-terms"
    if record["licence"]["review_state"] in {"pending", "unknown", "restricted"}:
        return f"licence-{record['licence']['review_state']}", "conditionally-free-pending-licence-decision"
    return "public-or-no-fee-path-to-reverify", "free-scope"


def geography_for(row: dict) -> str:
    category = row["category"]
    if category in {"space_weather", "astronomy"}:
        return "planetary-or-celestial; evaluate at the shared focus where applicable"
    if category in {"aviation", "surface_observation", "optional_observation", "optional_air_quality", "camera", "transport", "local_buoy", "tide_water_level"}:
        return "named stations or sites in/near the Avalon validation area; no inferred full-box coverage"
    if category in {"ocean", "wave", "surge", "marine", "marine_observation"}:
        return "marine portion of the evidence box; product-domain and land/sea selection must be proved"
    return "evidence box 45.0-50.5 N, 58.0-46.0 W; Avalon detail validation first"


def field_scope(row: dict) -> str:
    return f"{row['category']}; exact canonical fields remain limited to the source registry declaration and a task-specific field mapping"


def build_registered() -> list[dict]:
    rows = json.loads(AUDIT.read_text())
    source_module = runpy.run_path(str(ROOT / "experiments/st-johns-weather-map/registry/source_data.py"))
    records = {record["id"]: record for record in source_module["registry"]()["sources"]}
    result = []
    for row in rows:
        record = records[row["source_id"]]
        task = target_for(row)
        access, eligibility = access_for(row, record)
        implemented = row["implementation_category"] in {"functional_dispatch", "static_artifact_calculation"}
        contract_gap = (
            "live artifact, API readback, failure and provenance evidence remain unverified"
            if implemented
            else "no accepted source-specific product/access/field contract authorizes implementation"
        )
        if eligibility in {"recorded-disposition", "out-of-scope-paid"}:
            contract_gap = "no implementation authority requested; preserve the recorded exclusion or external disposition"
        result.append({
            "roster_id": f"registry:{row['source_id']}",
            "kind": "registered-source",
            "source_id": row["source_id"],
            "product_access_path": row["product"],
            "audit_ref": row["registry_evidence"],
            "implementation": {
                "category": row["implementation_category"],
                "adapter_registered": row["adapter_registered"],
                "evidence": row["implementation_evidence"],
                "fixture_status": row["registry_fixture_status"],
                "live_smoke_status": row["registry_live_smoke_status"],
            },
            "free_access": {"classification": access, "roster_disposition": eligibility},
            "prior_decision": {
                "registry_state": row["registry_status"],
                "schedulable": row["registry_schedulable"],
                "admission_condition": row["admission_condition"],
                "notes": row["notes"],
            },
            "field_family_scope": {
                "category": row["category"],
                "registry_variables": record["variables"],
                "constraint": "Only these declared names/levels are candidates; a target task must prove every selected upstream-to-canonical mapping and must correct stored-but-not-retrieved claims before serving them.",
            },
            "account_or_permission": record["authentication"],
            "licence": record["licence"],
            "geography": {"registry_coverage": record["coverage"], "roster_gate": geography_for(row)},
            "target_task": {
                "issue": task,
                "title": TASKS[task],
                "url": f"https://github.com/TusharSariya/Astraeus/issues/{task}",
            },
            "contract_status": {
                "accepted_authority": ["GOV-SPEC-001", "GOV-SPEC-002", "GOV-SPEC-004", "GOV-SPEC-005", "GOV-SPEC-006", "EVD-PROV-001", "EVD-MASK-001"],
                "draft_executable_contracts": ["artifact-ingestion", "evidence-truth-boundary", "source-registry-catalogue"],
                "gap": contract_gap,
            },
            "completion_proof": ["representative fixture", "upstream live retrieval", "validated immutable artifact", "Astraeus API readback", "failure and provenance evidence"],
            "operational": False,
        })
    return result


def clean_markdown(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("`", "").strip())


def slugify(value: str) -> str:
    value = clean_markdown(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:96]


def research_disposition(path: Path, line: int, name: str) -> tuple[str, int]:
    text = name.lower()
    if path.name == "unimplemented-sources-ai-commercial.md":
        if line >= 46:
            return "deferred-paid", 97
        if "weathernext 3" in text or "weathernext 2 native" in text or "weathernext 2 through" in text:
            return "free-in-scope", 77
        if "fourcastnet" in text and ("local" in text or "self" in text):
            return "tool-or-method", 95
        if "self-run" in text or "gencast" in text or "neuralgcm" in text or "fuxi" in text:
            return "future-generated-method", 95
        if "noaa oar aiwp archive" in text:
            return "historical", 94
        if "noaa ai-gfs" in text:
            return "free-in-scope", 96
        if "aifs ens" in text:
            return "free-in-scope", 82
        if "aifs single" in text:
            return "free-in-scope", 81
        if "hosted" in text or any(x in text for x in ("windborne", "silurian", "jua ", "brightband")):
            return "deferred-paid", 97
        return "recorded-research-disposition", 97
    if path.name == "unimplemented-sources-environmental.md":
        if 22 <= line <= 36:
            if "nl 511" in text:
                return "free-permission-required", 90
            if "hydrometric" in text:
                return "free-in-scope", 87
            if "thunderstorm" in text:
                return "free-in-scope", 80
            return "free-in-scope", 88
        if 42 <= line <= 54:
            if "radiosonde" in text:
                return "historical", 94
            if "ascat" in text:
                return "free-access-unverified", 87
            return "free-in-scope", 85
        if 60 <= line <= 79:
            if "commercial" in text:
                return "deferred-paid", 97
            return "free-in-scope-or-coverage-check", 87
        if 85 <= line <= 97:
            if "expanded deterministic" in text or "hrdps/rdps/gdps uv" in text:
                return "free-in-scope", 79
            if "open-meteo" in text or "lsa saf" in text:
                return "free-in-scope", 78
            if "licensed pollen" in text:
                return "deferred-paid", 97
            return "free-in-scope-or-account-gated", 86
        if 101 <= line <= 113:
            return "historical", 94
        if 117 <= line <= 121:
            return "free-in-scope-or-permission-check", 89
        if 125 <= line <= 125:
            return "free-permission-required", 90
        return "recorded-exclusion-or-unresolved-lead", 97
    # Geospatial/celestial appendix.
    if 37 <= line <= 54:
        if any(x in text for x in ("google routes", "google solar", "cesium ion", "phone panorama")):
            return "deferred-commercial-or-workflow", 97
        return "free-in-scope-or-coverage-check", 91
    if 70 <= line <= 73:
        return "free-in-scope", 92
    if 74 <= line <= 81:
        return "historical", 94
    if 82 <= line <= 88:
        return "future-module-free-source", 92
    return "recorded-exclusion-or-unresolved-lead", 97


def build_research_candidates() -> list[dict]:
    files = [
        ROOT / "docs/research/unimplemented-sources-ai-commercial.md",
        ROOT / "docs/research/unimplemented-sources-environmental.md",
        ROOT / "docs/research/unimplemented-sources-geospatial-celestial.md",
    ]
    result = []
    seen: dict[str, int] = {}
    for path in files:
        for line_number, raw in enumerate(path.read_text().splitlines(), 1):
            if not raw.startswith("|") or re.match(r"^\|\s*:?-", raw):
                continue
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            if not cells or cells[0] in {"Candidate", "Provider/product", "Source/product", "Researched source/product", "Source / product", "Source ID"}:
                continue
            if path.name == "unimplemented-sources-environmental.md" and line_number >= 143:
                continue
            name = clean_markdown(cells[0])
            base_slug = slugify(name)
            seen[base_slug] = seen.get(base_slug, 0) + 1
            slug = base_slug if seen[base_slug] == 1 else f"{base_slug}-{seen[base_slug]}"
            disposition, task = research_disposition(path, line_number, name)
            detail = clean_markdown(cells[1]) if len(cells) > 1 else ""
            result.append({
                "roster_id": f"research:{slug}",
                "kind": "researched-product-or-access-path",
                "source_id": None,
                "product_access_path": name,
                "audit_ref": f"docs/research/{path.name}:{line_number}",
                "implementation": {"category": "research-only-or-finer-than-registry", "finding": detail},
                "free_access": {"classification": disposition, "roster_disposition": disposition},
                "prior_decision": {"registry_state": None, "schedulable": False, "admission_condition": None, "notes": detail},
                "field_family_scope": "product-specific fields named by the research row; exact canonical mapping is an unresolved contract gate",
                "account_or_permission": "must be established from the cited product path before retrieval; no research mention grants access",
                "geography": "must prove relevance to the evidence box or named Avalon validation sites; wider research coverage is not admission",
                "target_task": {"issue": task, "title": TASKS[task], "url": f"https://github.com/TusharSariya/Astraeus/issues/{task}"},
                "contract_status": {
                    "accepted_authority": ["GOV-SPEC-001", "GOV-SPEC-002", "GOV-SPEC-004", "GOV-SPEC-005", "GOV-SPEC-006", "EVD-PROV-001", "EVD-MASK-001"],
                    "draft_executable_contracts": ["artifact-ingestion", "evidence-truth-boundary", "source-registry-catalogue"],
                    "gap": "unregistered or product/access-path granularity exceeds the registry; owner-approved source and field contract required before implementation",
                },
                "completion_proof": ["representative fixture", "upstream live retrieval", "validated immutable artifact", "Astraeus API readback", "failure and provenance evidence"],
                "operational": False,
            })
    # Historical and exclusion sections use bullets rather than tables. Each
    # bullet is retained as the audit's own product-family grouping.
    env = ROOT / "docs/research/unimplemented-sources-environmental.md"
    env_lines = env.read_text().splitlines()
    supplemental = list(SUPPLEMENTAL_RESEARCH_ROWS)
    for line_number in list(range(101, 114)) + list(range(129, 136)):
        raw = env_lines[line_number - 1]
        if not raw.startswith("- "):
            raise SystemExit(f"expected supplemental audit bullet at {env}:{line_number}")
        name = clean_markdown(raw[2:])
        disposition = "historical" if line_number <= 113 else "recorded-exclusion-or-unresolved-lead"
        task = 94 if line_number <= 113 else 97
        supplemental.append((f"environmental-narrative-{line_number}", name, f"docs/research/{env.name}:{line_number}", disposition, task))
    for slug, name, audit_ref, disposition, task in supplemental:
        result.append({
            "roster_id": f"research:{slug}",
            "kind": "researched-product-or-access-path",
            "source_id": None,
            "product_access_path": name,
            "audit_ref": audit_ref,
            "implementation": {"category": "research-only-narrative-group", "finding": "No source-specific production retrieval path was established by the audit."},
            "free_access": {"classification": disposition, "roster_disposition": disposition},
            "prior_decision": {"registry_state": None, "schedulable": False, "admission_condition": None, "notes": "Preserve the audit's grouped distinction; split only in the target task after exact product/access verification."},
            "field_family_scope": "grouped research scope only; exact products and canonical field mappings remain contract gaps",
            "account_or_permission": "unresolved unless the disposition explicitly excludes the path; no research mention grants access",
            "geography": "must prove evidence-box or Avalon relevance; exclusions and broader-region rows remain visible",
            "target_task": {"issue": task, "title": TASKS[task], "url": f"https://github.com/TusharSariya/Astraeus/issues/{task}"},
            "contract_status": {
                "accepted_authority": ["GOV-SPEC-001", "GOV-SPEC-002", "GOV-SPEC-004", "GOV-SPEC-005", "GOV-SPEC-006", "EVD-PROV-001", "EVD-MASK-001"],
                "draft_executable_contracts": ["artifact-ingestion", "evidence-truth-boundary", "source-registry-catalogue"],
                "gap": "no accepted source-specific contract; this row records research routing or an explicit disposition only",
            },
            "completion_proof": ["representative fixture", "upstream live retrieval", "validated immutable artifact", "Astraeus API readback", "failure and provenance evidence"],
            "operational": False,
        })
    return result


def validate(payload: dict) -> None:
    for relative, expected_hash in FROZEN_INPUT_HASHES.items():
        actual_hash = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise SystemExit(f"audit input changed and requires roster review: {relative} ({actual_hash})")
    audit = json.loads(AUDIT.read_text())
    expected = [row["source_id"] for row in audit]
    registered = payload["registered_sources"]
    actual = [row["source_id"] for row in registered]
    errors = []
    if len(expected) != 118:
        errors.append(f"audit has {len(expected)} registry rows, expected 118")
    if len(actual) != 118 or len(set(actual)) != 118:
        errors.append("roster must have 118 unique registered source ids")
    if set(expected) != set(actual):
        errors.append("roster registered ids differ from the audit")
    if len(payload["research_candidates"]) != 170:
        errors.append(f"roster must have 170 research candidate/group rows, got {len(payload['research_candidates'])}")
    roster_ids = [row["roster_id"] for row in registered + payload["research_candidates"]]
    if len(roster_ids) != len(set(roster_ids)):
        errors.append("roster_id values are not unique")
    required = {"free_access", "prior_decision", "field_family_scope", "account_or_permission", "geography", "target_task", "contract_status", "completion_proof", "operational"}
    for row in registered + payload["research_candidates"]:
        missing = required - set(row)
        if missing:
            errors.append(f"{row.get('roster_id')} missing {sorted(missing)}")
        if row.get("operational") is not False:
            errors.append(f"{row.get('roster_id')} must keep operational false")
        issue = row.get("target_task", {}).get("issue")
        if issue not in TASKS:
            errors.append(f"{row.get('roster_id')} has unknown target task {issue}")
    if errors:
        raise SystemExit("\n".join(errors))
    ticket_plan = json.loads(CHILD_TICKETS.read_text())
    seen_titles = set()
    for ticket in ticket_plan["create_now"]:
        if ticket["title"] in seen_titles:
            raise SystemExit(f"duplicate child title: {ticket['title']}")
        seen_titles.add(ticket["title"])
        if not ticket.get("key"):
            raise SystemExit(f"child ticket missing stable key: {ticket['title']}")
        if ticket["parent_issue"] not in {78, 85, 86, 87, 88, 91, 92, 96}:
            raise SystemExit(f"unexpected child parent: {ticket['parent_issue']}")
        if ticket["parent_issue"] in ticket["blocked_by_issues"]:
            raise SystemExit(f"child-parent dependency cycle: {ticket['title']}")
        for key in ("included_roster_scope", "excluded_scope", "blocked_by_issues"):
            if not ticket.get(key):
                raise SystemExit(f"{ticket['title']} missing {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        payload = {
            "schema_version": 1,
            "generated_from": "docs/research/unimplemented-sources-registry.json at audit commit 333d5e2",
            "authority": "planning roster only; research is non-normative and owner approval is required for source-specific behavior",
            "registered_sources": build_registered(),
            "research_candidates": build_research_candidates(),
        }
        validate(payload)
        OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        validate(json.loads(OUTPUT.read_text()))
    payload = json.loads(OUTPUT.read_text())
    print(json.dumps({
        "registered_sources": len(payload["registered_sources"]),
        "research_candidates": len(payload["research_candidates"]),
        "total_roster_rows": len(payload["registered_sources"]) + len(payload["research_candidates"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
