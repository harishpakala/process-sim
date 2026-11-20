"""Read-only qualification of approved cross-domain identifier mappings.

Mappings are authoritative declarations, not inferred joins. This module does
not select an intent, contact a model, or compile/execute SPARQL.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def load_cross_domain_mappings(path: str | Path) -> dict[str, dict]:
    """Load mapping IDs with strict structural validation; fail closed."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SelectionContractError("Cross-domain mappings must be a JSON array")
    registry = {}
    required = ("id", "left_domain", "right_domain", "left_property",
                "right_property", "evidence_ids")
    for record in records:
        if not isinstance(record, dict) or any(key not in record for key in required):
            raise SelectionContractError("Incomplete cross-domain mapping")
        if any(not isinstance(record[key], str) or not record[key].strip()
               for key in required[:-1]):
            raise SelectionContractError("Invalid cross-domain mapping fields")
        if not isinstance(record["evidence_ids"], list) or not record["evidence_ids"] or any(
                not isinstance(value, str) or not value.strip()
                for value in record["evidence_ids"]):
            raise SelectionContractError("Mapping lacks SHACL evidence references")
        # Optional owner-level approval evidence. An empty list means no
        # owner-specific correspondence has been independently approved.
        # This metadata does not change legacy property-level qualification.
        pairs = record.get("approved_owner_pairs")
        if "approved_owner_pairs" in record:
            if not isinstance(pairs, list):
                raise SelectionContractError("Owner-pair approvals must be an array")
            seen_pairs = set()
            for pair in pairs:
                if not isinstance(pair, dict) or set(pair) != {
                    "left_owner_shape_uri", "right_owner_shape_uri", "evidence_ids"
                }:
                    raise SelectionContractError("Invalid owner-pair approval fields")
                if any(not isinstance(pair[k], str) or not pair[k].strip()
                       for k in ("left_owner_shape_uri", "right_owner_shape_uri")):
                    raise SelectionContractError("Invalid owner-pair shape URI")
                evidence = pair["evidence_ids"]
                if (not isinstance(evidence, list) or not evidence
                        or any(not isinstance(e, str) or not e.strip() for e in evidence)
                        or len(evidence) != len(set(evidence))):
                    raise SelectionContractError("Owner-pair approval lacks distinct evidence")
                key = (pair["left_owner_shape_uri"], pair["right_owner_shape_uri"])
                if key in seen_pairs:
                    raise SelectionContractError("Duplicate owner-pair approval")
                seen_pairs.add(key)
        if record["id"] in registry:
            raise SelectionContractError("Duplicate cross-domain mapping ID")
        if record["left_domain"] == record["right_domain"]:
            raise SelectionContractError("Cross-domain mapping must connect distinct domains")
        registry[record["id"]] = record
    return registry


def qualify_cross_domain_mappings(registry: dict[str, dict],
                                  qualified_properties: dict[str, set[str]]) -> list[dict]:
    """Offer only approved mappings whose predicates exist in both qualified domains.

    qualified_properties maps domain name to the SHACL-verified predicate URIs
    available in its candidate subgraphs. This step does not rank mappings.
    """
    offered = []
    for mapping_id, mapping in sorted(registry.items()):
        if mapping.get("verified") is not True:
            continue
        left, right = mapping["left_domain"], mapping["right_domain"]
        if (mapping["left_property"] not in qualified_properties.get(left, set()) or
                mapping["right_property"] not in qualified_properties.get(right, set())):
            continue
        offered.append({
            "id": mapping_id,
            "left_domain": left,
            "right_domain": right,
            "left_property": mapping["left_property"],
            "right_property": mapping["right_property"],
            "identifier_type": ("AssetIdentifier" if mapping_id.endswith("-asset-identifier")
                                else "ProductIdentifier" if mapping_id.endswith("-product-identifier")
                                else "declared mapping"),
        })
    return offered


def validate_cross_domain_mapping_selection(mapping_id: str, offered: list[dict],
                                            registry: dict[str, dict]) -> dict:
    """Resolve a model-selected ID against both the offered set and source registry."""
    if not isinstance(mapping_id, str):
        raise SelectionContractError("Mapping selection must be a mapping ID")
    if sum(item["id"] == mapping_id for item in offered) != 1:
        raise SelectionContractError("Selected mapping was not offered")
    mapping = registry.get(mapping_id)
    if mapping is None or mapping.get("verified") is not True:
        raise SelectionContractError("Selected mapping is not verified")
    selected = next(item for item in offered if item["id"] == mapping_id)
    if any(mapping[key] != selected[key] for key in
           ("left_domain", "right_domain", "left_property", "right_property")):
        raise SelectionContractError("Selected mapping differs from approved evidence")
    return mapping
