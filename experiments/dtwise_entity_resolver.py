#!/usr/bin/env python3
"""Graph-grounded EBOM V2 equipment-tag resolver.

Resolve explicit engineering identifiers to unique source records and recorded
assembly contexts. No tag-to-assembly aliases or string matching.
"""
import json
import re
from pathlib import Path
from urllib.parse import quote
from rdflib import Graph, Literal, Namespace, RDF, URIRef

CORE = Namespace("https://example.org/dtwise/core/")
EBOM = Namespace("https://example.org/engineeringbom/")
DEFAULT_GRAPH = "https://example.org/dtwise/graph/ebom-v2"
TAG = re.compile(r"[A-Z]{1,6}[-_][0-9]{1,8}\Z")

def normalize_tag(tag):
    value = tag.strip().upper().replace("_", "-")
    if not TAG.fullmatch(value):
        raise ValueError("INVALID_ENTITY_TAG: expected an explicit engineering tag")
    return value

def resolve_local(rdf_graph, tag):
    """Return a unique equipment record and context, or fail closed."""
    tag = normalize_tag(tag)
    matches = []
    for node in rdf_graph.subjects(EBOM.hasEngineeringLocalId, Literal(tag)):
        if (node, RDF.type, CORE.BOMItemRecord) not in rdf_graph:
            continue
        for assembly in rdf_graph.objects(node, CORE.hasRecordedParent):
            if (assembly, RDF.type, CORE.AssemblyRecord) in rdf_graph:
                matches.append((str(node), str(assembly)))
    matches = sorted(set(matches))
    if not matches:
        raise ValueError("ENTITY_NOT_FOUND: " + tag)
    if len(matches) != 1:
        raise ValueError("AMBIGUOUS_ENTITY: " + tag)
    return {"tag": tag, "equipment_uri": matches[0][0],
            "assembly_uri": matches[0][1]}

def resolution_sparql(tag, graph_uri=DEFAULT_GRAPH):
    tag = normalize_tag(tag)
    if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", graph_uri):
        raise ValueError("INVALID_GRAPH_URI")
    return f"""PREFIX core: <https://example.org/dtwise/core/>
PREFIX ebom: <https://example.org/engineeringbom/>
SELECT DISTINCT ?equipment ?assembly WHERE {{
  GRAPH <{graph_uri}> {{
    ?equipment a core:BOMItemRecord ;
      ebom:hasEngineeringLocalId {json.dumps(tag)} ;
      core:hasRecordedParent ?assembly .
    ?assembly a core:AssemblyRecord .
  }}
}}"""

def resolve_remote(tag, endpoint="http://localhost:7200/repositories/AAS", graph_uri=DEFAULT_GRAPH):
    import requests
    response = requests.post(endpoint, data={"query": resolution_sparql(tag, graph_uri)},
                             headers={"Accept": "application/sparql-results+json"}, timeout=45)
    response.raise_for_status()
    matches = response.json()["results"]["bindings"]
    if not matches:
        raise ValueError("ENTITY_NOT_FOUND: " + normalize_tag(tag))
    if len(matches) != 1:
        raise ValueError("AMBIGUOUS_ENTITY: " + normalize_tag(tag))
    return {"tag": normalize_tag(tag),
            "equipment_uri": matches[0]["equipment"]["value"],
            "assembly_uri": matches[0]["assembly"]["value"]}
