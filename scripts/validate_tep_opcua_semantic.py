#!/usr/bin/env python3
"""Validate TEP OPC UA semantic identity and documented inventory associations.

Only reads semantic/instances/tep and semantic/templates.
Exit 0 means structural consistency, NOT verified physical equivalence or live OPC UA.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "semantic"
INSTANCE = ROOT / "instances" / "tep"
CANONICAL = re.compile(r"^https://aas\\.example\\.com/[A-Za-z0-9]+$")
EXPECTED = {
    "TI_105": "PROPOSED_EQUIVALENCE_REQUIRES_REVIEW",
    "VC_105": "UNRESOLVED_TAG_DISCREPANCY",
    "VC_107": "PROPOSED_EQUIVALENCE_REQUIRES_REVIEW",
    "VC_111": "PROPOSED_EQUIVALENCE_REQUIRES_REVIEW",
    "SC_101": "RELATED_CONTROL_NOT_SAME_ASSET",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def records(model, group=None):
    for section in model.get("submodelElements", []):
        if group and section.get("idShort") != group:
            continue
        for item in section.get("value", []):
            if item.get("modelType") == "SubmodelElementCollection":
                props = {p["idShort"]: p.get("value") for p in item.get("value", [])
                         if p.get("modelType") == "Property"}
                props["_record"] = item.get("idShort")
                yield props


def main():
    opc = list(records(load(INSTANCE / "tep_opcua_connectivity_instance.json"), "SignalMappings"))
    dex = list(records(load(INSTANCE / "tep_dexpi_instance.json")))
    ecad = list(records(load(INSTANCE / "tep_ecad_instance.json"), "Devices"))
    inventory = list(records(load(INSTANCE / "tep_asset_inventory_instance.json"), "Assets"))
    bom = list(records(load(INSTANCE / "tep_engineering_bom_instance.json"), "BOMItems"))
    template = load(ROOT / "templates" / "opcua_connectivity_template.json")
    template_fields = {p.get("idShort") for group in template.get("submodelElements", [])
                       if group.get("idShort") == "SignalMappings"
                       for item in group.get("value", []) for p in item.get("value", [])}
    required = {"AssetIdentifier", "EngineeringFunctionId", "OPCUANodeId",
                "SignalName", "RelatedInventoryAssetIdentifier",
                "InventoryAssociationStatus", "InventoryAssociationEvidence"}
    errors = []
    if required - template_fields:
        errors.append(f"Template missing fields: {sorted(required - template_fields)}")
    if len(opc) != 34:
        errors.append(f"Expected 34 OPC UA mappings, got {len(opc)}")

    dex_by_tag = {r["LocalId"]: r for r in dex if r.get("LocalId") and r.get("AssetIdentifier")}
    inv_by_id = {r["AssetIdentifier"]: r for r in inventory if r.get("AssetIdentifier")}
    ecad_ids = {r["AssetIdentifier"] for r in ecad if r.get("AssetIdentifier")}
    bom_keys = {(r.get("SourceDomain"), r.get("EngineeringLocalId"), r.get("AssetIdentifier"))
                for r in bom}
    counts = Counter()
    nodes, signals = set(), set()
    review = []
    for r in opc:
        tag, asset = r.get("EngineeringFunctionId"), r.get("AssetIdentifier")
        if not tag or not isinstance(asset, str) or not CANONICAL.fullmatch(asset):
            errors.append(f"{r['_record']}: invalid tag or canonical AssetIdentifier")
            continue
        if dex_by_tag.get(tag, {}).get("AssetIdentifier") == asset:
            counts["DEXPI"] += 1
        else:
            errors.append(f"{tag}: DEXPI mismatch")
        if ("DEXPI", tag, asset) in bom_keys:
            counts["BOM"] += 1
        else:
            errors.append(f"{tag}: Engineering BOM mismatch")
        if asset in ecad_ids:
            counts["ECAD_EXACT"] += 1
        for field, seen in (("OPCUANodeId", nodes), ("SignalName", signals)):
            value = r.get(field)
            if not value or value in seen:
                errors.append(f"{tag}: missing or duplicate {field}: {value}")
            else:
                seen.add(value)
        if asset in inv_by_id:
            counts["INVENTORY_EXACT"] += 1
            if tag in EXPECTED:
                errors.append(f"{tag}: expected reviewed relationship but now exact identity")
            continue
        related = r.get("RelatedInventoryAssetIdentifier")
        status = r.get("InventoryAssociationStatus")
        evidence = r.get("InventoryAssociationEvidence")
        if related not in inv_by_id or status != EXPECTED.get(tag) or not evidence:
            errors.append(f"{tag}: invalid inventory association: {related}, {status}")
            continue
        counts["INVENTORY_DOCUMENTED"] += 1
        counts[status] += 1
        review.append((tag, related, status))

    if len(review) != len(EXPECTED) or {x[0] for x in review} != set(EXPECTED):
        errors.append("Unexpected number or identity of review-required associations")
    if counts["DEXPI"] != 34 or counts["BOM"] != 34:
        errors.append("Not all mappings match DEXPI and Engineering BOM")
    if counts["INVENTORY_EXACT"] + counts["INVENTORY_DOCUMENTED"] != 34:
        errors.append("Not all inventory relationships accounted for")
    print("OPC UA mappings:", len(opc))
    print("DEXPI exact matches:", counts["DEXPI"])
    print("Engineering BOM matches:", counts["BOM"])
    print("ECAD exact matches:", counts["ECAD_EXACT"])
    print("AssetInventory exact matches:", counts["INVENTORY_EXACT"])
    print("Documented inventory associations:", counts["INVENTORY_DOCUMENTED"])
    print("Unique OPC UA NodeIds:", len(nodes))
    print("Inventory mappings accounted for:", counts["INVENTORY_EXACT"] + counts["INVENTORY_DOCUMENTED"], "/ 34")
    for tag, related, status in review:
        print("REVIEW:", tag, "->", related, status)
    for error in errors:
        print("ERROR:", error, file=sys.stderr)
    if errors:
        print("FAIL: Structural validation errors")
        return 1
    print("PASS: Structural cross-domain validation")
    print("REVIEW REQUIRED: Documented associations are not confirmed asset identities.")
    print("Live OPC UA connectivity was not tested.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        sys.exit(1)
