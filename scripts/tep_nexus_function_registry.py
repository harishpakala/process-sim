"""Evidence-gated multi-function registry and live GraphDB resolver.

The two local reports are *run-scoped snapshots*. Every selected mapping is
also rechecked against GraphDB before querying TimescaleDB.
"""
import json
from pathlib import Path

import requests

from tep_nexus_mapping_discovery import SPARQL, classify_bindings


def load_supported_functions(discovery_path, coverage_path, run_id):
    discovery = json.loads(Path(discovery_path).read_text(encoding="utf-8-sig"))
    coverage = json.loads(Path(coverage_path).read_text(encoding="utf-8-sig"))
    if discovery.get("mapping_confidence") != "PROVISIONAL_NOT_PHYSICALLY_VERIFIED":
        raise ValueError("Unrecognized mapping discovery report")
    if coverage.get("run_id") != run_id or coverage.get("shared_run_provenance") != "NOT_VERIFIED":
        raise ValueError("Temporal coverage is not scoped to the requested run")
    if coverage.get("physical_sensor_binding") != "NOT_VERIFIED":
        raise ValueError("Unexpected physical binding assertion")
    coverage_by_function = {x["engineering_function"]: x for x in coverage["functions"]}
    if len(coverage_by_function) != len(coverage["functions"]):
        raise ValueError("Duplicate functions in temporal coverage")
    registry = {}
    for candidate in discovery["candidates"]:
        function = candidate["engineering_function"]
        if candidate["status"] != "UNIQUE_PROVISIONAL_CANDIDATE" or len(candidate["mappings"]) != 1:
            continue
        temporal = coverage_by_function.get(function)
        if not temporal or temporal.get("mapping_status") != "UNIQUE_PROVISIONAL_CANDIDATE":
            continue
        signals = temporal.get("signals", [])
        mapping = candidate["mappings"][0]
        if (temporal.get("temporal_coverage_status") != "HAS_SAMPLES"
                or len(signals) != 1
                or signals[0].get("signal") != mapping["operational_signal"]
                or signals[0].get("sample_count", 0) <= 0):
            continue
        if function in registry:
            raise ValueError("Duplicate engineering function in discovery")
        registry[function] = mapping
    if not registry:
        raise ValueError("No supported functions with mapping and temporal coverage")
    return registry


def resolve_supported_mapping(graphdb_url, function, registry):
    """Resolve a function from current GraphDB data, matching approved snapshot."""
    if function not in registry:
        raise ValueError("Engineering function not in run-scoped registry")
    response = requests.post(
        graphdb_url, data={"query": SPARQL},
        headers={"Accept": "application/sparql-results+json"}, timeout=30,
    )
    response.raise_for_status()
    classified = classify_bindings(response.json()["results"]["bindings"])
    matches = [x for x in classified["candidates"] if x["engineering_function"] == function]
    if len(matches) != 1 or matches[0]["status"] != "UNIQUE_PROVISIONAL_CANDIDATE":
        raise RuntimeError("GraphDB mapping missing or ambiguous for selected function")
    live = matches[0]["mappings"][0]
    if live != registry[function]:
        raise RuntimeError("GraphDB mapping changed since discovery; regenerate reports")
    return {
        "engineering_function": function,
        "function_reference": live["function_reference"],
        "operational_signal": live["operational_signal"],
        "asset_uri": live["asset_uri"],
        "mapping_status": "PROVISIONAL_ENGINEERING_MATCH",
        "mapping_source": "GraphDB AAS repository",
        "resolution_method": "path-constrained SPARQL; snapshot equality check",
    }
