"""Read-only referential-integrity audit for SELiRA asset and product AAS submodels."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping


UNASSIGNED_REVIEW = "UNASSIGNED_SIMULATION_ONLY_REVIEW_REQUIRED"


@dataclass(frozen=True)
class InventoryCatalogFinding:
    asset: str
    status: str
    product_reference: str | None
    product: str | None
    detail: str


def _field(entry: Mapping[str, Any], name: str) -> str | None:
    return next((p.get("value") for p in entry.get("value", [])
                 if p.get("idShort") == name and p.get("modelType") == "Property"), None)


def _collection(submodel: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    return next((e.get("value", []) for e in submodel.get("submodelElements", [])
                 if e.get("idShort") == name), [])


def audit_inventory_catalog(
    inventory: Mapping[str, Any], catalog: Mapping[str, Any],
) -> list[InventoryCatalogFinding]:
    """Check primary product links without treating references as product approvals.

    ProductReference and CandidateProductReference are the only primary links.
    Historical and proposed replacement links are not substituted silently.
    """
    products = _collection(catalog, "Products")
    product_ids = [_field(p, "ProductIdentifier") for p in products]
    counts = Counter(x for x in product_ids if x)
    index = {_field(p, "ProductIdentifier"): p.get("idShort") for p in products
             if _field(p, "ProductIdentifier")}
    results = []
    for asset in _collection(inventory, "Assets"):
        name = asset.get("idShort", "")
        direct = _field(asset, "ProductIdentifier")
        candidate = _field(asset, "CandidateProductReference")
        ref = direct or candidate
        if direct and candidate and direct != candidate:
            status, detail = "conflicting_references", "Primary and candidate references disagree"
        elif not ref:
            marker = _field(asset, "ProductAssignmentStatus")
            if marker == UNASSIGNED_REVIEW and _field(asset, "ModelingStatus") == "SimulationOnly":
                status, detail = "unassigned_review", "Simulation-only signal requires product policy review"
            else:
                status, detail = "missing_assignment", "No primary catalog product reference"
        elif counts[ref] > 1:
            status, detail = "ambiguous_product", "Catalog product identifier is duplicated"
        elif ref not in index:
            status, detail = "broken_reference", "Referenced product is absent from catalog"
        else:
            status, detail = "linked_unverified", "Reference resolves; engineering suitability not established"
        results.append(InventoryCatalogFinding(name, status, ref, index.get(ref), detail))
    return results
