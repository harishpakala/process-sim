"""Experimental single GraphDB SELECT for engineering identity and OPCUA mapping.

This narrow query returns engineering identifiers and their live signal mapping
in one request. It is not a replacement for arbitrary SHACL graph traversals.
"""
from __future__ import annotations

import json
import re

from process_sim.dtwise.rdf_executor import execute_select

_DEXPI = re.compile(r"^[A-Za-z]{2}_[0-9]+$")
_ECAD = re.compile(r"^(?:FI|LI|PI|TI)-[0-9]+$")


def compile_entity_signal_query(domain: str, local_id: str, *, evidence: dict) -> str:
    """Compile a fixed, read-only mapping SELECT from an evidenced entity."""
    if domain not in ("DEXPI", "ECAD"):
        raise ValueError("Unsupported domain")
    if not isinstance(local_id, str) or not (
        _DEXPI.fullmatch(local_id) if domain == "DEXPI" else _ECAD.fullmatch(local_id)
    ):
        raise ValueError("Invalid engineering LocalId")
    if not isinstance(evidence, dict) or not evidence.get("properties"):
        raise ValueError("SHACL evidence required for entity resolution")
    namespace = "https://example.org/dexpi/" if domain == "DEXPI" else "https://example.org/ecad/"
    entity_type = ("  ?entity a eng:InstrumentationFunction ;\n"
                   if domain == "DEXPI" else "  ?entity ")
    # Fixed vocabulary and JSON-quoted literal: never interpolate model paths.
    return (
        f"PREFIX eng: <{namespace}>\n"
        "PREFIX opcua: <https://example.org/opcuaconnectivity/>\n"
        "SELECT DISTINCT ?entity ?assetIdentifier ?signalName WHERE {\n"
        " GRAPH ?engineeringGraph {\n"
        + entity_type +
        "eng:hasLocalId ?localId ;\n"
        "          eng:hasAssetIdentifier ?assetIdentifier .\n"
        " }\n"
        " GRAPH ?mappingGraph {\n"
        "  ?mapping opcua:hasAssetIdentifier ?assetIdentifier ;\n"
        "           opcua:hasSignalName ?signalName .\n"
        " }\n"
        f" FILTER(STR(?localId) = {json.dumps(local_id)})\n"
        "}\nORDER BY ?entity ?assetIdentifier ?signalName"
    )


def resolve_entity_signal(endpoint, domain, local_id, *, evidence, executor=execute_select):
    """Require one unique live asset/signal pair; multiple entity IRIs allowed."""
    query = compile_entity_signal_query(domain, local_id, evidence=evidence)
    rows = executor(endpoint, query)
    if not isinstance(rows, list):
        raise ValueError("Invalid GraphDB mapping response")
    pairs = set()
    entities = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"entity", "assetIdentifier", "signalName"}:
            raise ValueError("Unexpected GraphDB mapping columns")
        if not all(isinstance(row[k], str) and row[k].strip() for k in row):
            raise ValueError("Empty GraphDB mapping value")
        entities.add(row["entity"])
        pairs.add((row["assetIdentifier"], row["signalName"]))
    if len(pairs) != 1 or len(entities) != 1:
        raise ValueError("Missing or ambiguous live engineering/signal mapping")
    asset, signal = next(iter(pairs))
    return {
        "domain": domain, "engineering_function": local_id,
        "entity": next(iter(entities)), "asset_identifier": asset,
        "operational_signal": signal,
        "sparql": query, "resolution_method": "single_graphdb_entity_signal_select",
        "physical_sensor_binding": "NOT_VERIFIED",
    }
