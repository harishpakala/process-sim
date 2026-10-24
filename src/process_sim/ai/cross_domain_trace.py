"""Evidence-first cross-domain catalog and operational traceability.

ECLASS identifiers label terms. Catalog values are manufacturer claims; no
numeric limits, units, or measurement equivalence are inferred.
"""
from __future__ import annotations

import re
from uuid import UUID

def validate_trace_plan(plan):
    if not isinstance(plan, dict) or set(plan) not in (
        {"operation", "assetId"}, {"operation", "assetId", "runId", "limit"}
    ) or plan.get("operation") != "asset_trace":
        raise ValueError("Expected asset_trace with assetId and optional runId/limit")
    asset_id = plan["assetId"]
    if not isinstance(asset_id, str) or not 1 <= len(asset_id) <= 512 or not re.fullmatch(
        r"[A-Za-z0-9_:/#.%+~-]+", asset_id
    ):
        raise ValueError("Invalid assetId")
    if ("runId" in plan) != ("limit" in plan):
        raise ValueError("runId and limit must be provided together")
    result = dict(plan)
    if "runId" in plan:
        try:
            result["runId"] = str(UUID(plan["runId"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid runId") from exc
        if type(plan["limit"]) is not int or not 1 <= plan["limit"] <= 5000:
            raise ValueError("Invalid limit")
    return result

def execute_trace_plan(plan, graphdb_endpoint, *, specs_reader=None, history_reader=None,
                       alignment_declarations=()):
    p = validate_trace_plan(plan)
    if specs_reader is None:
        from process_sim.api.asset_specifications import asset_specifications
        specs_reader = asset_specifications
    specs = specs_reader(p["assetId"], graphdb_endpoint)
    if not isinstance(specs, dict):
        raise ValueError("Unexpected specifications response")
    status = specs.get("linkStatus")
    if status not in ("linked", "unresolved", "not_specified"):
        raise ValueError("Unexpected product link status")
    catalog = []
    for prop in specs.get("technicalSpecifications", []):
        catalog.append({
            "iri": prop.get("iri"), "name": prop.get("name"),
            "catalogValue": prop.get("value"),
            "semanticIds": prop.get("semanticIds", []),
            "supplementalSemanticIds": prop.get("supplementalSemanticIds", []),
            "source": "ProductCatalog", "comparisonStatus": "not_validated",
        })
    result = {
        "operation": "asset_trace", "assetId": p["assetId"],
        "assetIri": specs.get("assetIri"), "product": specs.get("product"),
        "productLinkStatus": status, "productReference": specs.get("productReference"),
        "catalogProperties": catalog,
        "semanticPolicy": "ECLASS references identify terms; they do not supply operating limits.",
        "comparisonStatus": "not_validated",
        "comparisonReasons": ["No verified property-to-signal quantity alignment",
                              "No verified unit and applicability mapping"],
        "sources": ["AssetInventory", "ProductCatalog"],
    }
    if "runId" not in p:
        return result
    result["runId"] = p["runId"]
    if not specs.get("assetIri"):
        result["historyStatus"] = "missing_asset_iri"
        return result
    if history_reader is None:
        from process_sim.api.asset_history import asset_history
        history_reader = asset_history
    history = history_reader(specs["assetIri"], p["runId"], p["limit"])
    if history.get("status") not in ("mapped", "unmapped", "ambiguous"):
        raise ValueError("Unexpected history mapping status")
    result["historyStatus"] = history["status"]
    result["operationalEvidence"] = {
        "references": history.get("references", []),
        "signalCandidates": history.get("signals", []),
        "signal": history.get("signal") if history["status"] == "mapped" else None,
        "points": history.get("points", []) if history["status"] == "mapped" else [],
        "faultEvents": history.get("faultEvents", []) if history["status"] == "mapped" else [],
    }
    from .property_alignment import assess_alignments
    result["propertyAlignments"] = assess_alignments(
        catalog, result["operationalEvidence"]["signal"], alignment_declarations)
    result["sources"].append("TimescaleDB")
    return result
