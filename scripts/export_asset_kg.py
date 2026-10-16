#!/usr/bin/env python3
"""Export TEP AAS inventory and product catalog as RDF Turtle (stdlib only).

Usage: python3 scripts/export_asset_kg.py
Output: examples/kg/tep_asset_product_graph.ttl
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://example.org/tep/kg/"
PRED = BASE + "vocab/"
OUTPUT = ROOT / "examples/kg/tep_asset_product_graph.ttl"


def properties(record):
    return {field["idShort"]: field.get("value", "") for field in record.get("value", [])
            if field.get("modelType") == "Property"}


def iri(value):
    return "<" + value.replace(">", "%3E").replace("<", "%3C") + ">"


def literal(value):
    return json.dumps(str(value), ensure_ascii=False)


def triple(subject, predicate, obj, resource=False):
    predicate_iri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" if predicate == "rdfType" else PRED + predicate
    return f"{iri(subject)} {iri(predicate_iri)} {iri(obj) if resource else literal(obj)} ."


def upload_to_graphdb(endpoint):
    """Append generated Turtle triples to a GraphDB repository."""
    statements_url = endpoint.rstrip("/") + "/statements"
    request = urllib.request.Request(
        statements_url,
        data=OUTPUT.read_bytes(),
        headers={"Content-Type": "text/turtle; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"Uploaded RDF to {statements_url} (HTTP {response.status})")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GraphDB upload failed: HTTP {exc.code}: {body}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true", help="POST generated Turtle to GraphDB")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"),
        help="GraphDB repository SPARQL URL",
    )
    args = parser.parse_args()

    inventory = json.loads((ROOT / "examples/aas/asset_inventory_instance.json").read_text())
    catalog = json.loads((ROOT / "examples/aas/product_catalog_instance.json").read_text())
    products = [properties(p) for p in catalog["submodelElements"][0]["value"]]
    assets = [properties(a) for a in inventory["submodelElements"][0]["value"]]
    ids = {p["AssetIdentifier"] for p in products}
    lines = ["# Generated from the AAS JSON examples; not evidence of a deployed GraphDB.", ""]
    for p in products:
        subject = p["AssetIdentifier"]
        lines.append(triple(subject, "rdfType", BASE + "ProductType", True))
        for key in ("ManufacturerName", "ManufacturerPartNumber"):
            if p.get(key):
                lines.append(triple(subject, key, p[key]))
    linked = 0
    for a in assets:
        subject = a["AssetId"]
        lines.append(triple(subject, "rdfType", BASE + "SimulatedAsset", True))
        for key in ("AssetName", "EquipmentTag", "AssetType", "ModelingStatus",
                    "SimulationStatus", "MonitoringStatus", "FaultInjectionStatus",
                    "FaultDetectionStatus", "PLCMapping"):
            if a.get(key):
                lines.append(triple(subject, key, a[key]))
        if a.get("OperationalReference"):
            signal = BASE + "signals/" + quote(a["OperationalReference"], safe="")
            lines.append(triple(subject, "hasOperationalSignal", signal, True))
            lines.append(triple(signal, "signalId", a["OperationalReference"]))
        status_id = "https://example.org/tep/status/" + quote(a.get("OperationalReference") or a["AssetId"].rsplit("/", 1)[-1], safe="")
        lines.append(triple(subject, "hasAssetInventoryStatus", status_id, True))
        lines.append(triple(status_id, "rdfType", BASE + "AssetInventoryStatus", True))
        for status_key in ("ModelingStatus", "SimulationStatus", "MonitoringStatus", "FaultInjectionStatus", "FaultDetectionStatus"):
            if a.get(status_key):
                lines.append(triple(status_id, status_key, a[status_key]))
        product = a.get("ProductReference")
        if product:
            if product not in ids:
                raise ValueError(f"Unresolved ProductReference: {product}")
            lines.append(triple(subject, "hasProductType", product, True))
            linked += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(assets)} assets, {len(products)} product types, {linked} links")
    if args.upload:
        upload_to_graphdb(args.endpoint)


if __name__ == "__main__":
    main()
