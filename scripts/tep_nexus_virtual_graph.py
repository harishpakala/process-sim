"""Deterministic offline virtual-graph projection of TEP NEXUS query evidence.

This module does not issue SQL/SPARQL or materialize historian observations.
Live IDs use source-key hashes; offline fallback uses ordinals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

BASE = "https://example.org/tep-nexus/virtual/"


def _uri(*parts):
    return BASE + "/".join(quote(str(part), safe="") for part in parts)


def project(query):
    evidence = query["temporalEvidence"]
    mapping = query["engineeringMapping"]
    plan = query["validatedPlan"]
    run = str(UUID(evidence["runId"]))
    function = plan["engineering_function"]
    signal = evidence["signal"]
    if mapping["engineering_function"] != function:
        raise ValueError("Engineering mapping does not match validated plan")
    if mapping["operational_signal"] != signal:
        raise ValueError("Engineering mapping does not match historian signal")
    if not mapping.get("asset_uri") and not mapping.get("asset_identifier"):
        raise ValueError("Missing source asset reference")

    nodes = {}
    edges = []

    def node(node_id, kind, **attrs):
        if node_id in nodes:
            if nodes[node_id] != {"id": node_id, "type": kind, **attrs}:
                raise ValueError("Conflicting virtual resource identity")
        else:
            nodes[node_id] = {"id": node_id, "type": kind, **attrs}

    def edge(source, predicate, target):
        if source not in nodes or target not in nodes:
            raise ValueError("Dangling virtual graph edge")
        item = {"source": source, "predicate": predicate, "target": target}
        if item not in edges:
            edges.append(item)

    domain = mapping.get("domain")
    f = _uri("function", domain, function) if domain else _uri("function", function)
    s = _uri("signal", signal)
    r = _uri("run", run)
    asset = mapping.get("asset_uri") or _uri("asset-identifier", mapping["asset_identifier"])
    node(f, "EngineeringFunction", localId=function, source="GraphDB",
         mappingConfidence="PROVISIONAL", **({"domain": domain} if domain else {}))
    node(s, "OperationalSignal", signalId=signal, source="GraphDB mapping / TimescaleDB key",
         physicalSensorBinding="NOT_VERIFIED")
    node(r, "SimulationRun", runId=run, identitySource="operator_supplied",
         sharedRunProvenance="NOT_VERIFIED")
    if mapping.get("asset_uri"):
        node(asset, "EngineeringAsset", source="GraphDB", physicalIdentity="NOT_VERIFIED")
    else:
        node(asset, "AssetIdentifier", identifier=mapping["asset_identifier"], source="GraphDB", physicalIdentity="NOT_VERIFIED")
    edge(f, "mapsToSignal", s)
    edge(f, "associatedWithAsset" if mapping.get("asset_uri") else "hasAssetIdentifier", asset)
    edge(r, "hasSignal", s)

    for i, command in enumerate(evidence.get("faultCommands", [])):
        event_id = command.get("event_id")
        if not event_id:
            raise ValueError("Fault command lacks event_id")
        e = _uri("run", run, "command", event_id)
        node(e, "RecordedFaultCommand", source="TimescaleDB fault_events",
             eventId=event_id, action=command["action"],
             simulationTimeHours=command["simulation_time_hours"],
             observedAt=command["observed_at"],
             faultId=command.get("fault_id"), faultType=command.get("fault_type"),
             target=command.get("target"), magnitude=command.get("magnitude"),
             eventSource=command.get("event_source"),
             physicalFaultState="NOT_VERIFIED")
        edge(r, "hasRecordedCommand", e)

    for window_index, window in enumerate(evidence["windows"]):
        for ordinal, sample in enumerate(window["samples"]):
            # A sample can appear in overlapping windows. This identity is
            # intentionally scoped to the query window and ordinal.
            o = (_uri("run", run, "signal", signal, "observation", sample["observationPrimaryKeyHash"])
                 if sample.get("observationPrimaryKeyHash") else
                 _uri("run", run, "signal", signal, "observation", sample["observationFingerprint"])
                 if sample.get("observationFingerprint") else
                 _uri("run", run, "window", window_index, "observation", ordinal))
            node(o, "VirtualObservation", source="TimescaleDB signal_samples",
                 identityScope=("SOURCE_COMPOSITE_PRIMARY_KEY_SHA256"
                                if sample.get("observationPrimaryKeyHash") else
                                "CONTENT_FINGERPRINT_NOT_DATABASE_PRIMARY_KEY"
                                if sample.get("observationFingerprint") else
                                "QUERY_WINDOW_ORDINAL_NOT_DATABASE_PRIMARY_KEY"),
                 contentFingerprint=sample.get("observationFingerprint"),
                 simulationTimeHours=sample["simulationTimeHours"],
                 observedAt=sample["observedAt"], value=sample["value"],
                 signalUnits="NOT_VERIFIED", windowIndex=window_index,
                 truncatedWindow=bool(window["truncated"]))
            edge(o, "observesSignal", s)
            edge(o, "belongsToRun", r)
            for relation in sample.get("temporalRelations", []):
                if relation["relation"] not in {
                    "BEFORE", "AFTER", "DURING", "DURING_UNCONFIRMED",
                    "AFTER_UNCONFIRMED", "UNKNOWN",
                }:
                    raise ValueError("Unsupported temporal relation")
                # Relation is an annotation, not an inferred physical state.
                nodes[o].setdefault("temporalRelations", []).append(dict(relation))

    return {
        "interface": "TEP NEXUS offline virtual graph projection v1",
        "materializedInGraphDB": False,
        "snapshotScope": "single supplied query evidence JSON",
        "nodes": list(nodes.values()),
        "edges": edges,
        "limitations": [
            "Live observation IDs use source-key hashes; offline fallback IDs may be query-window ordinals.",
            "GraphDB does not directly expose these observations via SPARQL.",
            "Engineering mapping is provisional; physical binding and shared run provenance are not verified.",
            "Recorded fault commands do not establish physical fault causation.",
        ],
    }


def enrich_semantic(graph, initial_mapping, mappings):
    """Merge validated signal mappings without modifying observation evidence."""
    from copy import deepcopy
    result = deepcopy(graph)
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = result["edges"]
    signal = initial_mapping["operational_signal"]
    signal_id = _uri("signal", signal)
    initial_key = (initial_mapping["domain"], initial_mapping["engineering_function"])
    matches = [m for m in mappings if (m["domain"], m["engineering_function"]) == initial_key]
    if len(matches) != 1 or matches[0]["asset_identifier"] != initial_mapping["asset_identifier"]:
        raise ValueError("Initial mapping changed during semantic enrichment")
    def add_node(n):
        if n["id"] in nodes and nodes[n["id"]] != n:
            raise ValueError("Conflicting enriched node")
        nodes[n["id"]] = n
    def add_edge(source, predicate, target):
        if source not in nodes or target not in nodes:
            raise ValueError("Dangling enriched edge")
        edge = dict(source=source, predicate=predicate, target=target)
        if edge not in edges:
            edges.append(edge)
    for m in mappings:
        if m["operational_signal"] != signal:
            raise ValueError("Enrichment signal mismatch")
        f = _uri("function", m["domain"], m["engineering_function"])
        a = _uri("asset-identifier", m["asset_identifier"])
        add_node(dict(id=f, type="EngineeringFunction", localId=m["engineering_function"],
                      domain=m["domain"], source="GraphDB", mappingConfidence="PROVISIONAL"))
        add_node(dict(id=a, type="AssetIdentifier", identifier=m["asset_identifier"],
                      source="GraphDB", physicalIdentity="NOT_VERIFIED"))
        add_edge(f, "mapsToSignal", signal_id)
        add_edge(f, "hasAssetIdentifier", a)
    result["nodes"] = list(nodes.values())
    result["semanticEnrichment"] = "complete"
    result["capabilities"]["R02"] = result["capabilities"]["R01"] and len(mappings) > 1
    result["capabilities"]["R03"] = len({m["domain"] for m in mappings}) > 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="reports/tep_nexus_fault_relative_query.json")
    parser.add_argument("--output", default="reports/tep_nexus_virtual_graph.json")
    args = parser.parse_args()
    report = project(json.loads(Path(args.query).read_text(encoding="utf-8-sig")))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(out), "nodes": len(report["nodes"]),
                      "edges": len(report["edges"]),
                      "materializedInGraphDB": False}, indent=2))


if __name__ == "__main__":
    main()
