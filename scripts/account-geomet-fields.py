#!/usr/bin/env python3
"""Build the issue-145 GeoMet field reconciliation from bounded snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

WMS = "{http://www.opengis.net/wms}"
WCS = "{http://www.opengis.net/wcs/2.0}"


def text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_wcs(path: Path) -> tuple[set[str], str | None]:
    root = ET.parse(path).getroot()
    ids = {text(node) for node in root.iter(f"{WCS}CoverageId")}
    ids.discard(None)
    return ids, root.attrib.get("updateSequence")


def parse_wms(path: Path) -> tuple[dict[str, dict], str | None, str | None]:
    root = ET.parse(path).getroot()
    layers: dict[str, dict] = {}
    service_title = text(root.find(f"{WMS}Service/{WMS}Title"))
    for layer in root.iter(f"{WMS}Layer"):
        name = text(layer.find(f"{WMS}Name"))
        if not name:
            continue
        title = text(layer.find(f"{WMS}Title"))
        abstract = text(layer.find(f"{WMS}Abstract"))
        bbox_node = layer.find(f"{WMS}EX_GeographicBoundingBox")
        bbox = None
        if bbox_node is not None:
            bbox = {
                "west": float(text(bbox_node.find(f"{WMS}westBoundLongitude"))),
                "south": float(text(bbox_node.find(f"{WMS}southBoundLatitude"))),
                "east": float(text(bbox_node.find(f"{WMS}eastBoundLongitude"))),
                "north": float(text(bbox_node.find(f"{WMS}northBoundLatitude"))),
            }
        dimensions = {
            node.attrib.get("name", ""): {
                "extent": text(node),
                "default": node.attrib.get("default"),
                "units": node.attrib.get("units"),
            }
            for node in layer.findall(f"{WMS}Dimension")
            if node.attrib.get("name")
        }
        identifier = layer.find(f"{WMS}Identifier")
        layers[name] = {
            "title": title,
            "abstract": abstract,
            "geographic_bbox_wgs84": bbox,
            "dimensions": dimensions,
            "provider_identifier": text(identifier),
            "provider_identifier_authority": identifier.attrib.get("authority") if identifier is not None else None,
        }
    return layers, root.attrib.get("updateSequence"), service_title


def family(coverage_id: str) -> str:
    if coverage_id.startswith("HRDPS-WEonG_"):
        return "hrdps-weong-2.5km"
    if coverage_id.startswith("HRDPS."):
        return "hrdps-continental-2.5km"
    if coverage_id.startswith("RDPS_10km_"):
        return "rdps-10km"
    if coverage_id.startswith("RDPS-WEonG_"):
        return "rdps-weong-10km"
    if coverage_id.startswith("GDPS_15km_"):
        return "gdps-15km"
    if coverage_id.startswith("GDPS-WEonG_"):
        return "gdps-weong-15km"
    if coverage_id.startswith("GDPS-GEML_25km_"):
        return "gdps-geml-25km"
    return "unresolved"


def semantics(title: str | None) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    match = re.search(r"\s*\[([^\]]+)\]\s*$", title)
    unit = match.group(1).strip() if match else None
    meaning = title[: match.start()].strip() if match else title.strip()
    if " - " in meaning:
        meaning = meaning.split(" - ", 1)[1].strip()
    return meaning, unit


def level(coverage_id: str, meaning: str | None) -> dict | None:
    # Product IDs contain horizontal resolutions such as ``10km`` and
    # ``2.5km``.  Level classification therefore uses the provider's semantic
    # title first and cannot treat those product tokens as vertical levels.
    source = meaning or ""
    patterns = (
        (r"between\s+(\d+(?:\.\d+)?)\s*(?:mb|hPa)\s+and\s+(\d+(?:\.\d+)?)\s*(?:mb|hPa)", "pressure_interval", "hPa"),
        (r"(?:at |[._])(\d+(?:\.\d+)?)\s*(?:mb|hPa)\b", "pressure", "hPa"),
        (r"(?:at |[._])(\d+(?:\.\d+)?)\s*m(?: above (?:ground|surface))?\b", "height", "m"),
        (r"(?:at |[._])(\d+(?:\.\d+)?)\s*km\b", "height", "km"),
        (r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*cm", "depth_interval", "cm"),
    )
    for pattern, kind, unit in patterns:
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            values = [float(value) for value in match.groups()]
            return {"kind": kind, "values": values, "unit": unit, "source": "wms_title"}
    named = next((value for value in ("mean sea level", "surface", "entire atmosphere", "planetary boundary layer") if meaning and value in meaning.lower()), None)
    return {"kind": "named", "value": named, "source": "wms_title"} if named else None


def topic(meaning: str | None) -> str:
    value = (meaning or "").lower()
    groups = (
        ("cloud_visibility_astronomy", ("cloud", "visibility", "sky state", "seeing", "transparency", "fog")),
        ("thermodynamic_profile", ("temperature", "humidity", "dew point", "geopotential", "pressure", "vertical velocity", "thickness", "mixing ratio", "ozone")),
        ("wind_profile", ("wind", "vorticity", "helicity", "shear")),
        ("precipitation_hydrology", ("precip", "rain", "snow", "runoff", "water equivalent")),
        ("radiation_surface_energy", ("radiation", "radiative", "heat flux", "heat net flux", "albedo", "uv index", "incoming visible")),
        ("land_ocean_ice", ("soil", "land", "sea", "ice", "surface temperature")),
        ("convective_diagnostic", ("cape", "convective available potential energy", "cin", "lifted", "showalter", "sweat", "thunderstorm", "storm severity", "severe storm", "severe weather", "equilibrium level", "convection", "most unstable parcel", "height of the lcl")),
        ("human_exposure_diagnostic", ("ventilation index", "universal thermal climate index")),
    )
    return next((name for name, needles in groups if any(needle in value for needle in needles)), "unresolved_provider_quantity")


def route(prior: dict, current: bool, meaning: str | None, unit: str | None, lev: dict | None, product: str) -> tuple[str, list[int], str]:
    if not current:
        return "removed_from_current_capabilities", [145, 97], "Historical ID is absent from the dated current WCS capabilities; no retrieval may be scheduled from this path."
    if prior["disposition"] == "advertised-selected-capability":
        return "covered_by_issue_79_experimental_acquisition", [79, 141, 97], "Issue 79 retrieved this selected ID once; issue 141 owns source identity, field-window and semantic admission, and issue 97 owns final coverage verification."
    if unit is None:
        return "blocked_by_issue_141_unstated_unit_or_class_semantics", [141, 97], "The current WMS title states no bracketed unit. Preserve the provider title and values without abbreviation-based inference; issue 141 must resolve semantics before field admission."
    if product == "gdps-geml-25km":
        return "needs_gdps_geml_product_disposition", [194, 141, 97], "This is the separate GDPS-GEML 25 km product. Owner review must establish relevance versus the current GDPS product before any implementation child."
    value_topic = topic(meaning)
    is_vertical = lev is not None and lev["kind"] in {"pressure", "pressure_interval", "height"}
    if is_vertical and value_topic == "thermodynamic_profile":
        return "candidate_child_vertical_thermodynamics", [{"hrdps-continental-2.5km": 187, "rdps-10km": 188, "gdps-15km": 189}[product], 141, 97], "Use the exact stated level and unit in a bounded thermodynamic-profile child; compare native producer access before choosing the server-rectified WCS path."
    if is_vertical and value_topic in {"wind_profile", "unresolved_provider_quantity"}:
        return "candidate_child_vertical_wind_and_dynamics", [{"hrdps-continental-2.5km": 187, "rdps-10km": 188, "gdps-15km": 189}[product], 141, 97], "Use the exact stated level and unit in a bounded wind/dynamics child; compare native producer access before choosing the server-rectified WCS path."
    if value_topic == "convective_diagnostic":
        return "candidate_child_convective_diagnostics", [190, 141, 97], "Keep the provider diagnostic as issued in a focused convective-diagnostics child; do not infer ranking or thresholds."
    if value_topic == "precipitation_hydrology":
        return "candidate_child_precipitation_and_hydrology", [191, 141, 97], "Preserve stated accumulation or quantity semantics in a focused precipitation/hydrology child; do not derive rates from amounts."
    if value_topic in {"radiation_surface_energy", "land_ocean_ice", "human_exposure_diagnostic"}:
        return "candidate_child_surface_energy_land_ocean", [192, 141, 97], "Preserve the exact provider quantity in a focused surface-energy/land/ocean child; no conversions or scoring admission are implied."
    return "candidate_child_surface_state_and_visibility", [193, 141, 97], "Preserve the exact provider quantity in a focused surface-state/visibility child; compare native producer access before choosing WCS."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--wcs", type=Path, required=True)
    parser.add_argument("--wms", type=Path, required=True)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    historical_doc = json.loads(args.historical.read_text())
    capture_receipt = json.loads(args.capture_receipt.read_text())
    for name, path in (("wcs", args.wcs), ("wms", args.wms)):
        receipt = capture_receipt["captures"][name]
        if receipt["sha256"] != sha256(path) or receipt["decoded_body_bytes"] != path.stat().st_size:
            raise ValueError(f"{name} capability input does not match its capture receipt")
    historical = {row["coverage_id"]: row for row in historical_doc["full_family_inventory"]}
    current_wcs, wcs_sequence = parse_wcs(args.wcs)
    wms, wms_sequence, service_title = parse_wms(args.wms)
    family_prefixes = (
        "HRDPS.", "HRDPS-WEonG_", "RDPS_10km_", "RDPS-WEonG_",
        "GDPS_15km_", "GDPS-WEonG_", "GDPS-GEML_25km_",
    )
    current_family = {item for item in current_wcs if item.startswith(family_prefixes)}

    rows = []
    for coverage_id, prior in sorted(historical.items()):
        metadata = wms.get(coverage_id, {}) if coverage_id in current_wcs else {}
        meaning, unit = semantics(metadata.get("title"))
        lev = level(coverage_id, meaning)
        product = family(coverage_id)
        disposition, issues, reason = route(prior, coverage_id in current_wcs, meaning, unit, lev, product)
        rows.append({
            "coverage_id": coverage_id,
            "producer": "Environment and Climate Change Canada / Meteorological Service of Canada",
            "producer_product": product,
            "historical_2026_09_05": {"advertised": True, "selection": prior["disposition"], "proposed_variable": prior.get("variable")},
            "current_2026_09_06": {
                "advertised_wcs": coverage_id in current_wcs,
                "wms_metadata_present": coverage_id in wms,
                "title": metadata.get("title"),
                "semantic_quantity": meaning,
                "published_unit": unit,
                "published_unit_status": "verbatim_bracketed_wms_title" if unit else "not_stated_in_wms_title_unresolved",
                "level": lev,
                "level_status": "parsed_from_wms_title" if lev else "no_vertical_level_stated_in_wms_title",
                "topic": topic(meaning),
                "geography": metadata.get("geographic_bbox_wgs84"),
                "time": metadata.get("dimensions", {}).get("time"),
                "reference_time": metadata.get("dimensions", {}).get("reference_time"),
                "provider_identifier": metadata.get("provider_identifier"),
            },
            "access": {
                "metadata": "GeoMet WMS 1.3.0 GetCapabilities",
                "numeric_values": "GeoMet WCS 2.0.1 GetCoverage",
                "credential": "none advertised",
                "fees": "none advertised",
                "licence": "Environment and Climate Change Canada Data Server End-use Licence",
                "licence_url": "https://eccc-msc.github.io/open-data/licence/readme_en/",
            },
            "representation": {
                "kind": "numeric_coverage",
                "model_native_grid": False,
                "server_rectified_or_resampled": True,
                "rendered_image": False,
                "reason": "GeoMet WCS serves a rectified coverage and supports server clipping, reprojection and scaling; it is not the producer model's native GRIB grid.",
            },
            "disposition": disposition,
            "linked_issues": issues,
            "disposition_reason": reason,
        })

    additions = []
    for coverage_id in sorted(current_family - historical.keys()):
        metadata = wms.get(coverage_id, {})
        meaning, unit = semantics(metadata.get("title"))
        additions.append({
            "coverage_id": coverage_id,
            "producer_product": family(coverage_id),
            "title": metadata.get("title"),
            "semantic_quantity": meaning,
            "published_unit": unit,
            "disposition": "new_since_2026_09_05_requires_separate_review",
            "linked_issues": [145, 97],
        })

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["producer_product"], []).append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_files = []
    for product, product_rows in sorted(grouped.items()):
        product_path = args.output.with_name(f"{args.output.stem}-{product}{args.output.suffix}")
        payload = json.dumps({"schema_version": 1, "producer_product": product, "historical_ids": product_rows}, indent=2, ensure_ascii=False) + "\n"
        product_path.write_text(payload)
        output_files.append({"producer_product": product, "path": product_path.name, "records": len(product_rows), "sha256": hashlib.sha256(payload.encode()).hexdigest()})
    output = {
        "schema_version": 1,
        "generated_at": max(value for value in (wcs_sequence, wms_sequence) if value),
        "scope": "Issue 145 reconciliation of the 1,289 GeoMet deterministic-family IDs captured on 2026-09-05",
        "authority": "Non-normative provider research; no source admission or production capability claim",
        "source_receipts": {
            "historical_ledger": {"captured_at": historical_doc.get("retrieved_at"), "sha256": sha256(args.historical), "record_count": len(historical)},
            "previous_wcs_snapshot": {"url": "https://geo.weather.gc.ca/geomet?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities", "query": [["SERVICE", "WCS"], ["VERSION", "2.0.1"], ["REQUEST", "GetCapabilities"]], "client_completion": "unknown", "server_date_header": "Sun, 06 Sep 2026 06:54:59 GMT", "update_sequence": "2026-09-06T06:30:01Z", "sha256": "4d5126be17ab115e6b0312db9369f181c1631ab437921d401b55e3a238d9c7a0", "bytes": 1090094},
            "previous_wms_snapshot": {"url": "https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities", "query": [["SERVICE", "WMS"], ["VERSION", "1.3.0"], ["REQUEST", "GetCapabilities"]], "client_completion": "unknown", "server_date_header": "Sun, 06 Sep 2026 06:54:59 GMT", "update_sequence": "2026-09-06T06:15:01Z", "sha256": "330a2c744bd47fac5e02ab3b6d0c1c94e779b1129728c7707ad9e66c6c4aed85", "bytes": 37105809},
            "capture_operation": {
                "operation_received_byte_cap": capture_receipt["operation_received_byte_cap"],
                "operation_received_bytes": capture_receipt["operation_received_bytes"],
                "scratch_free_bytes_before": capture_receipt["scratch_free_bytes_before"],
                "scratch_free_bytes_after": capture_receipt["scratch_free_bytes_after"],
                "retry_counts": capture_receipt["retry_counts"],
            },
            "current_wcs": {
                **{key: value for key, value in capture_receipt["captures"]["wcs"].items() if key != "scratch_path"},
                "update_sequence": wcs_sequence,
                "coverage_count": len(current_wcs),
            },
            "current_wms": {
                **{key: value for key, value in capture_receipt["captures"]["wms"].items() if key != "scratch_path"},
                "update_sequence": wms_sequence,
                "service_title": service_title,
                "named_layer_count": len(wms),
            },
        },
        "accounting": {"historical_ids": len(rows), "historical_selected": sum(row["historical_2026_09_05"]["selection"] == "advertised-selected-capability" for row in rows), "historical_deferred": sum(row["historical_2026_09_05"]["selection"] == "advertised-capability-only-deferred" for row in rows), "current_family_ids": len(current_family), "removed_historical_ids": sum(not row["current_2026_09_06"]["advertised_wcs"] for row in rows), "new_current_ids": len(additions), "dispositions": dict(sorted(counts.items()))},
        "existing_issue_boundaries": {
            "79": "the already retrieved 245 selected deterministic GeoMet fields and reusable WCS geometry/acquisition evidence",
            "141": "GeoMet source identity, field/lead window, units/classes, and production admission",
            "97": "final integrated native/source coverage verification",
            "133": "RAQDPS/RDAQA only; no deterministic HRDPS/RDPS/GDPS IDs duplicated here",
            "134": "HRDPA/HREPA precipitation analyses only",
            "135": "HRDLPS/CaLDAS land products only",
            "136": "RDPA native geometry only",
            "147": "REPS member fields only",
            "148": "GEPS producer reductions only",
        },
        "removed_historical_ids": [
            row["coverage_id"] for row in rows
            if not row["current_2026_09_06"]["advertised_wcs"]
        ],
        "historical_id_files": output_files,
        "new_current_ids": additions,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
