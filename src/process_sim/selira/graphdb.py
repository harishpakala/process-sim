"""Read operational-reference candidates from GraphDB without trusting them.

GraphDB is a source of candidate links, not independent validation evidence.
No temporal samples are fetched until a separate consumer authorizes use.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .resolution import resolve_correspondence

ASSET_NS = "https://example.org/assetinventory/"
DEFAULT_ENDPOINT = "http://localhost:7200/repositories/AAS"
_IRI = re.compile(r"https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]{1,2048}\Z")


def fetch_operational_references(asset_iri: str, *, endpoint: str | None = None) -> list[str]:
    """Read bounded GraphDB references for an asset; fail on malformed responses."""
    if not isinstance(asset_iri, str) or not _IRI.fullmatch(asset_iri):
        raise ValueError("Invalid asset IRI")
    endpoint = endpoint or os.environ.get("GRAPHDB_SPARQL_ENDPOINT", DEFAULT_ENDPOINT)
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("Invalid GraphDB endpoint")
    query = (
        "SELECT DISTINCT ?reference WHERE { GRAPH ?g { <" + asset_iri + "> "
        "<" + ASSET_NS + "hasOperationalReference> ?reference . } } LIMIT 100"
    )
    request = Request(
        endpoint,
        data=urlencode({"query": query}).encode("utf-8"),
        headers={"Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    bindings = payload["results"]["bindings"]
    if not isinstance(bindings, list) or len(bindings) > 100:
        raise ValueError("Invalid GraphDB bindings")
    references = []
    for item in bindings:
        value = item["reference"]["value"]
        if not isinstance(value, str):
            raise ValueError("Invalid operational reference")
        references.append(value)
    return sorted(set(references))


def resolve_graphdb_correspondence(
    asset_iri: str, requested_property: str, *, declarations=(), endpoint=None
):
    """Qualify GraphDB candidate references using separately supplied declarations.

    Declarations are still reviewer assertions; this does not authenticate them.
    GraphDB errors propagate rather than silently becoming a validated mapping.
    """
    references = fetch_operational_references(asset_iri, endpoint=endpoint)
    return resolve_correspondence(requested_property, references, declarations)
