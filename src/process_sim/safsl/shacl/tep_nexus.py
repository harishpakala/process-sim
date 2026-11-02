"""Bridge SAFSL SC-01 to the existing TEP NEXUS lifecycle evidence model.

Unlike the illustrative compiler example, this adapter uses the repository's
real AAS template JSON IDs and the existing GraphDB snapshot reader. Source
identifiers are RDF literals, compared lexically, as in the existing SC-01
reference engine. No remote writes are performed.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from selira_integration.graphdb_snapshot import read_snapshot
from selira_integration.lifecycle import Snapshot, check
from process_sim.safsl.shacl.compiler import CompilationError, parse_contract, decode_template_id

ROOT = Path(__file__).resolve().parents[4]
TEMPLATES = {
    "assets": ROOT / "semantic/templates/asset_inventory_template.json",
    "products": ROOT / "semantic/templates/product_catalog_template.json",
}
FIELD_NAMES = {"assets": "ProductIdentifier", "products": "ProductIdentifier"}
VERDICTS = {
    "VALIDATED": "V",
    "INVALID": "F",
    "INDETERMINATE": "U",
    "NOT_APPLICABLE": "NA",
}


def _fields(template):
    def walk(elements):
        for element in elements or []:
            yield element.get("idShort")
            yield from walk(element.get("value") if isinstance(element.get("value"), list) else [])
    return set(walk(template.get("submodelElements")))


def real_contract_source():
    """Build SC-01 SAFSL against IDs actually declared by the repository."""
    identifiers = {}
    for alias, path in TEMPLATES.items():
        template = json.loads(path.read_text(encoding="utf-8"))
        if FIELD_NAMES[alias] not in _fields(template):
            raise CompilationError(f"Missing expected AAS field {FIELD_NAMES[alias]} in {path}")
        identifiers[alias] = base64.b64encode(template["id"].encode("utf-8")).decode("ascii")
    return f"""Specification AssetProductIntegrity {{
 Ref SubmodelTemplate assets = "{identifiers['assets']}";
 Ref SubmodelTemplate products = "{identifiers['products']}";
 Contract SC_01 {{
  forall asset in assets {{
   existsExactlyOne product in products
    where matches(asset.ProductIdentifier, product.ProductIdentifier);
  }}
 }}
}}"""


def verify_real_contract(source: str):
    """Check template references and field names against real local templates."""
    spec = parse_contract(source)
    if len(spec.contracts) != 1 or spec.contracts[0].identifier != "SC_01":
        raise CompilationError("Expected exactly the SC_01 contract")
    references = {r.alias: decode_template_id(r.identifier) for r in spec.templates}
    if set(references) != set(TEMPLATES):
        raise CompilationError("SC_01 must reference assets and products")
    for alias, path in TEMPLATES.items():
        template = json.loads(path.read_text(encoding="utf-8"))
        if references[alias] != template["id"]:
            raise CompilationError(f"Stale AAS template identifier: {alias}")
    rule = spec.contracts[0].rule
    if (rule.focus_alias, rule.product_alias, rule.left_field, rule.right_field) != (
        "assets", "products", "ProductIdentifier", "ProductIdentifier"
    ):
        raise CompilationError(
            "SC_01 must match AssetInventory.ProductIdentifier "
            "to ProductCatalog.ProductIdentifier"
        )
    return references


def evaluate_snapshot(snapshot: Snapshot, *, source=None):
    """Read-only per-asset V/F/U/NA; incomplete catalog is U, never F."""
    verify_real_contract(real_contract_source() if source is None else source)
    return {asset: VERDICTS[check(snapshot, asset)]
            for asset in sorted(snapshot.assigned)}


def evaluate_graphdb(endpoint, inventory_graph, catalog_graph, revision, *,
                     catalog_completeness_attested=False, source=None):
    """Read existing named graphs. Completeness is a caller attestation."""
    snapshot = read_snapshot(
        endpoint, inventory_graph, catalog_graph, revision,
        complete=catalog_completeness_attested
    )
    return evaluate_snapshot(snapshot, source=source)
