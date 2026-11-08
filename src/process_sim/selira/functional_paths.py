"""Read evidence-qualified DEXPI-to-ECAD functional paths from GraphDB.

A matching graph path establishes structural consistency, not physical asset
identity, authenticated provenance, or a verified live OPC UA binding.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .graphdb import DEFAULT_ENDPOINT

QUERY = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX opcua: <https://example.org/opcuaconnectivity/>
PREFIX ai: <https://example.org/assetinventory/>
PREFIX ecad: <https://example.org/ecad/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?dexpiId ?dexpiLabel ?signal ?plcAddress ?ecadId
       ?ecadDescription ?ecadDeviceType ?mappingStatus
       ?dexpiGraph ?opcuaGraph ?inventoryGraph ?ecadGraph
WHERE {
  GRAPH ?dexpiGraph {
    ?function dexpi:hasLocalId ?dexpiId ;
              dexpi:hasAssetIdentifier ?assetId ;
              rdfs:label ?dexpiLabel .
  }
  GRAPH ?opcuaGraph {
    ?mapping opcua:hasEngineeringFunctionReference ?assetId ;
             opcua:hasSignalName ?signal ;
             opcua:hasMappingStatus ?mappingStatus .
  }
  GRAPH ?inventoryGraph {
    ?inventoryAsset ai:hasOperationalReference ?inventorySignal ;
                    ai:hasPLCMapping ?plcAddress .
    FILTER(STR(?inventorySignal) = STR(?signal))
  }
  GRAPH ?ecadGraph {
    ?plcEndpoint ecad:hasAddress ?plcAddress ;
                 ecad:hasRole "InputChannel" .
    ?terminal ecad:isConnectedTo ?plcEndpoint .
    ?points ecad:hasEndPoint ?terminal .
    ?device ecad:hasConnectionPoints ?points ;
            ecad:hasLocalId ?ecadId ;
            ecad:hasDescription ?ecadDescription ;
            ecad:hasDeviceType ?ecadDeviceType .
  }
}
LIMIT 1000
"""


def fetch_functional_paths(*, endpoint=None):
    """Retrieve bounded structural paths; fail rather than silently trust errors."""
    endpoint = endpoint or os.environ.get("GRAPHDB_SPARQL_ENDPOINT", DEFAULT_ENDPOINT)
    if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
        raise ValueError("Invalid GraphDB endpoint")
    request = Request(
        endpoint,
        data=urlencode({"query": QUERY}).encode("utf-8"),
        headers={"Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        bindings = json.load(response)["results"]["bindings"]
    if not isinstance(bindings, list) or len(bindings) > 1000:
        raise ValueError("Invalid GraphDB bindings")
    fields = ("dexpiId", "dexpiLabel", "signal", "plcAddress", "ecadId",
              "ecadDescription", "ecadDeviceType", "mappingStatus",
              "dexpiGraph", "opcuaGraph", "inventoryGraph", "ecadGraph")
    paths = []
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Malformed GraphDB binding")
        try:
            row = {field: binding[field]["value"] for field in fields}
        except (KeyError, TypeError) as exc:
            raise ValueError("Incomplete GraphDB correspondence") from exc
        if any(not isinstance(value, str) or not value for value in row.values()):
            raise ValueError("Invalid GraphDB correspondence value")
        paths.append(row)
    return paths


def assess_functional_paths(paths, function_ids):
    """Qualify structural evidence without promoting provisional OPC UA mappings.

    Missing functions are unresolved; multiple distinct signal/address/device
    tuples are ambiguous. Even unique paths remain unverified operationally.
    """
    if not isinstance(paths, (list, tuple)):
        raise ValueError("Expected correspondence paths")
    if not isinstance(function_ids, (list, tuple)) or any(
        not isinstance(value, str) or not value for value in function_ids
    ):
        raise ValueError("Expected function identifiers")
    required = {"dexpiId", "signal", "plcAddress", "ecadId", "mappingStatus",
                "dexpiGraph", "opcuaGraph", "inventoryGraph", "ecadGraph"}
    for row in paths:
        if not isinstance(row, dict) or not required.issubset(row) or any(
            not isinstance(row[key], str) or not row[key] for key in required
        ):
            raise ValueError("Malformed correspondence path")
    result = {}
    for function_id in function_ids:
        matches = [row for row in paths if row["dexpiId"] == function_id]
        alternatives = {(row["signal"], row["plcAddress"], row["ecadId"])
                        for row in matches}
        statuses = {row["mappingStatus"] for row in matches}
        if not matches:
            status = "unresolved"
        elif len(alternatives) != 1 or len(statuses) != 1:
            status = "ambiguous"
        elif statuses == {"PROVISIONAL_ENGINEERING_MATCH"}:
            status = "structurally_supported_provisional"
        else:
            status = "unverified_mapping_status"
        result[function_id] = {
            "status": status,
            "operational_binding": "unverified",
            "consumer_authorized": False,
            "paths": matches,
            "limitations": [
                "Graph joins do not prove physical device identity.",
                "Named graphs do not authenticate source provenance.",
                "Live OPC UA binding and configuration applicability are not verified.",
            ],
        }
    return result


def resolve_functional_paths(function_ids, *, endpoint=None, reader=None):
    """Fetch and assess without authorizing downstream operational use."""
    paths = (reader or fetch_functional_paths)(endpoint=endpoint)
    return assess_functional_paths(paths, function_ids)
