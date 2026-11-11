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
CANONICAL = re.compile(r"^https://aas\.example\.com/[A-Za-z0-9]+$")
EXPECTED = {
    "TI_105": "PROPOSED_EQUIVALENCE_REQUIRES_REVIEW",
    "VC_105": "UNRESOLVED_TAG_DISCREPANCY",
    "VC_107": "PID_SUPPORTED_FUNCTIONAL_ASSOCIATION",
    "VC_111": "PID_SUPPORTED_FUNCTIONAL_ASSOCIATION",
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

    # Verify cross-domain reciprocal links and cited P&ID interpretation.
    dex_by_tag = {r.get("LocalId"): r for r in dex}
    ecad_by_id = {r.get("AssetIdentifier"): r for r in ecad}
    bom_by_key = {(r.get("SourceDomain"), r.get("AssetIdentifier")): r for r in bom}
    for mapping in opc:
        tag = mapping.get("EngineeringFunctionId")
        if tag not in EXPECTED:
            continue
        function_id = mapping.get("AssetIdentifier")
        related = mapping.get("RelatedInventoryAssetIdentifier")
        status = EXPECTED[tag]
        evidence = mapping.get("InventoryAssociationEvidence")
        if not evidence or "tep-reactor-pid.png" not in evidence:
            errors.append(f"{tag}: missing P&ID evidence reference")
        candidates = [
            ("DEXPI", dex_by_tag.get(tag), related),
            ("AssetInventory", inv_by_id.get(related), function_id),
            ("DEXPI BOM", bom_by_key.get(("DEXPI", function_id)), related),
        ]
        if tag != "SC_101":
            candidates.extend([
                ("ECAD", ecad_by_id.get(related), function_id),
                ("ECAD BOM", bom_by_key.get(("ECAD", related)), function_id),
            ])
        for domain, item, reciprocal in candidates:
            if not item:
                errors.append(f"{tag}: missing {domain} record")
            elif (item.get("RelatedAssetIdentifier") != reciprocal
                  or item.get("CrossDomainAssociationStatus") != status
                  or item.get("CrossDomainAssociationEvidence") != evidence
                  or not item.get("EngineeringInterpretationNote")):
                errors.append(f"{tag}: inconsistent {domain} association")
        if not mapping.get("EngineeringInterpretationNote"):
            errors.append(f"{tag}: missing OPC UA interpretation note")
    for name in ("dexpi", "ecad", "asset_inventory",
                 "engineering_bom", "opcua_connectivity"):
        model = load(ROOT / "templates" / (name + "_template.json"))
        fields = {p.get("idShort") for g in model.get("submodelElements", [])
                  for item in g.get("value", [])
                  for p in item.get("value", [])}
        if "EngineeringInterpretationNote" not in fields:
            errors.append(f"{name}: missing template interpretation note")


    # ECAD verification is a separate evidence assessment, not identity proof.
    ecad_model = load(INSTANCE / "tep_ecad_instance.json")
    device_group = next(g for g in ecad_model["submodelElements"]
                        if g["idShort"] == "Devices")
    net_group = next(g for g in ecad_model["submodelElements"]
                     if g["idShort"] == "ElectricalNets")
    schematic_group = next(g for g in ecad_model["submodelElements"]
                           if g["idShort"] == "Schematics")
    endpoint_paths = set()
    used_endpoints = set()
    for group in (device_group, net_group):
        for device in group["value"]:
            base = (group["idShort"], device["idShort"])
            endpoint_paths.add(base)
            for cp_group in device.get("value", []):
                if cp_group.get("idShort") == "ConnectionPoints":
                    for cp in cp_group.get("value", []):
                        endpoint_paths.add(base + ("ConnectionPoints", cp["idShort"]))
    for conn in schematic_group["value"]:
        relationships = [p for p in conn.get("value", [])
                         if p.get("modelType") == "RelationshipElement"]
        if len(relationships) != 1:
            errors.append(f"ECAD {conn['idShort']}: expected one relationship")
            continue
        rel = relationships[0]
        for side in ("first", "second"):
            keys = rel.get(side, {}).get("keys", [])
            path = tuple(k.get("value") for k in keys[1:])
            if path not in endpoint_paths:
                errors.append(f"ECAD {conn['idShort']}: invalid {side} endpoint {path}")
            else:
                used_endpoints.add(path)
    unused = [p for p in endpoint_paths if len(p) == 4 and p not in used_endpoints]
    if unused:
        errors.append(f"ECAD unconnected modeled connection points: {len(unused)}")
    ecad_template = load(ROOT / "templates" / "ecad_template.json")
    device_template = next(g for g in ecad_template["submodelElements"]
                           if g["idShort"] == "Devices")["value"][0]
    verification_fields = {"EngineeringVerificationStatus",
                           "EngineeringVerificationEvidence",
                           "ProductVerificationStatus",
                           "ProductVerificationEvidence"}
    if verification_fields - {p.get("idShort") for p in device_template["value"]}:
        errors.append("ECAD template missing verification fields")
    engineering_statuses = Counter()
    product_statuses = Counter()
    for d in ecad:
        tag = d.get("LocalId")
        if not all(d.get(k) for k in verification_fields):
            errors.append(f"ECAD {tag}: missing verification status/evidence")
        engineering_statuses[d.get("EngineeringVerificationStatus")] += 1
        product_statuses[d.get("ProductVerificationStatus")] += 1
    print("ECAD devices:", len(ecad))
    print("ECAD schematic connections:", len(schematic_group["value"]))
    print("ECAD modeled connection points:", sum(len(p) == 4 for p in endpoint_paths))
    print("ECAD invalid references:", sum("invalid" in e and "ECAD" in e for e in errors))
    for status, count in sorted(engineering_statuses.items()):
        print("ECAD ENGINEERING:", status, count)
    for status, count in sorted(product_statuses.items()):
        print("ECAD PRODUCT:", status, count)
    print("ECAD REVIEW REQUIRED: Engineering and product statuses are not physical or datasheet verification.")

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
