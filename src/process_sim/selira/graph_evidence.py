"""Inspect named-graph assertions; never treat storage as authentication."""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .graphdb import ASSET_NS, DEFAULT_ENDPOINT, _IRI
from .resolution import extract_signal
from .evidence_validator import validate_pressure_correspondence


def fetch_graph_evidence(asset_iri, *, endpoint=None):
    """Return graph and operational reference pairs from existing RDF predicate."""
    if not isinstance(asset_iri, str) or not _IRI.fullmatch(asset_iri):
        raise ValueError("Invalid asset IRI")
    endpoint = endpoint or DEFAULT_ENDPOINT
    if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
        raise ValueError("Invalid endpoint")
    query = ("SELECT DISTINCT ?g ?reference WHERE { GRAPH ?g { <" + asset_iri
             + "> <" + ASSET_NS + "hasOperationalReference> ?reference . } } LIMIT 100")
    request = Request(endpoint, data=urlencode({"query": query}).encode(),
                      headers={"Accept": "application/sparql-results+json",
                               "Content-Type": "application/x-www-form-urlencoded"},
                      method="POST")
    with urlopen(request, timeout=15) as response:
        bindings = json.load(response)["results"]["bindings"]
    if not isinstance(bindings, list) or len(bindings) > 100:
        raise ValueError("Invalid GraphDB bindings")
    rows = []
    for item in bindings:
        graph, reference = item["g"]["value"], item["reference"]["value"]
        if not isinstance(graph, str) or not graph or not isinstance(reference, str):
            raise ValueError("Malformed GraphDB assertion")
        rows.append({"graph": graph, "reference": reference})
    return sorted(rows, key=lambda row: (row["graph"], row["reference"]))


def check_graph_evidence(asset_iri, asset_tag, property_name, signal, *,
                         endpoint=None, reader=None):
    """Compare GraphDB references with project metadata; do not authorize use."""
    if not isinstance(asset_iri, str) or not _IRI.fullmatch(asset_iri):
        raise ValueError("Invalid asset IRI")
    metadata = validate_pressure_correspondence(asset_tag, property_name, signal)
    rows = (reader or fetch_graph_evidence)(asset_iri, endpoint=endpoint)
    if not isinstance(rows, (tuple, list)):
        raise ValueError("Invalid assertion collection")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"graph", "reference"} or any(
            not isinstance(row[k], str) or not row[k] for k in ("graph", "reference")
        ):
            raise ValueError("Malformed assertion")
    signals = {extract_signal(row["reference"]) for row in rows}
    signals.discard(None)
    if metadata.status == "rejected":
        status = "rejected"
    elif signals - {signal}:
        status = "conflicting_graph_assertions"
    elif metadata.status == "supported_project_scope" and signal in signals:
        status = "supported_graph_and_project_scope"
    else:
        status = "unresolved"
    return {"status": status, "assetIri": asset_iri, "signal": signal,
            "graphAssertions": rows, "metadata": metadata.to_dict(),
            "limitations": [
                "Named graph context does not authenticate engineering evidence.",
                "Source revision and configuration applicability are not verified.",
                "This result does not grant consumer authorization.",
            ]}
