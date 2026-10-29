"""Read SC-01 source snapshots from GraphDB using explicit named graphs.

The source properties are URI-shaped RDF *literals*. Preserve lexical values;
do not infer candidate assignments or invent a catalog-completeness assertion.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from .lifecycle import Snapshot

AI = "https://example.org/assetinventory/"
PC = "https://example.org/productcatalog/"

def _iri(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(x in value for x in "<>\r\n"):
        raise ValueError("Expected an absolute HTTP(S) named-graph IRI")
    return f"<{value}>"

def select(endpoint: str, query: str) -> list[dict]:
    request = Request(endpoint, data=urlencode({"query": query}).encode(),
                      headers={"Accept": "application/sparql-results+json"},
                      method="POST")
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    return [{name: binding["value"] for name, binding in row.items()}
            for row in data["results"]["bindings"]]

def snapshot_from_rows(revision: str, assigned_rows: list[dict],
                       catalog_rows: list[dict], *, complete: bool) -> Snapshot:
    assigned = {}
    catalog = {}
    for row in assigned_rows:
        asset, ref = row["asset"], row["ref"]
        if asset in assigned and assigned[asset] != ref:
            raise ValueError(f"Multiple assigned references for {asset}; SC-01 input is ambiguous")
        assigned[asset] = ref
    for row in catalog_rows:
        product, identifier = row["product"], row["identifier"]
        if product in catalog and catalog[product] != identifier:
            raise ValueError(f"Multiple identifiers for {product}; catalog evidence is ambiguous")
        catalog[product] = identifier
    return Snapshot(revision, assigned, catalog, complete=complete)

def read_snapshot(endpoint: str, inventory_graph: str, catalog_graph: str,
                  revision: str, *, complete: bool) -> Snapshot:
    inventory = _iri(inventory_graph)
    catalog = _iri(catalog_graph)
    assets = select(endpoint, f"""PREFIX ai: <{AI}>
SELECT ?asset ?ref WHERE {{ GRAPH {inventory} {{
 ?asset ai:hasProductReference ?ref .
}} }} ORDER BY ?asset ?ref""")
    products = select(endpoint, f"""PREFIX pc: <{PC}>
SELECT ?product ?identifier WHERE {{ GRAPH {catalog} {{
 ?product pc:hasAssetIdentifier ?identifier .
}} }} ORDER BY ?product ?identifier""")
    return snapshot_from_rows(revision, assets, products, complete=complete)

def save_snapshot(snapshot: Snapshot, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"revision": snapshot.revision,
        "assigned": snapshot.assigned, "catalog": snapshot.catalog,
        "complete": snapshot.complete}, indent=2, sort_keys=True), encoding="utf-8")

def load_snapshot(path: str | Path) -> Snapshot:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Snapshot(raw["revision"], raw["assigned"], raw["catalog"], raw["complete"])
