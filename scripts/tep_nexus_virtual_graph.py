"""Deterministic offline virtual-graph projection of TEP NEXUS query evidence.

This module does not issue SQL/SPARQL or materialize historian observations.
Observation IDs are snapshot-local ordinal identities, NOT database row IDs.
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
    if not mapping.get("asset_uri"):
        raise ValueError("Missing source asset URI")

    nodes = {}
    edges = []

    def node(identifier, kind, **attrs):
        if identifier in nodes:
            if nodes[identifier] != {"id": identifier, "type": kind, **attrs}:
                raise ValueError("Conflicting virtual resource identity")
        else:
            nodes[identifier] = {"id": identifier, "type": kind, **attrs}

    def edge(source, predicate, target):
        if source not in nodes or target not in nodes:
            raise ValueError("Dangling virtual graph edge")
        item = {"source": source, "predicate": predicate, "target": target}
        if item not in edges:
            edges.append(item)

    f = _uri("function", function)
    s = _uri("signal", signal)
    r = _uri("run", run)
    asset = mapping["asset_uri"]
    node(f, "EngineeringFunction", localId=function, source="GraphDB",
         mappingConfidence="PROVISIONAL")
    node(s, "OperationalSignal", signalId=signal, source="GraphDB mapping / TimescaleDB key",
         physicalSensorBinding="NOT_VERIFIED")
    node(r, "SimulationRun", runId=run, identitySource="operator_supplied",
         sharedRunProvenance="NOT_VERIFIED")
    node(asset, "EngineeringAsset", source="GraphDB", physicalIdentity="NOT_VERIFIED")
    edge(f, "mapsToSignal", s)
    edge(f, "associatedWithAsset", asset)
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
             physicalFaultState="NOT_VERIFIED")
        edge(r, "hasRecordedCommand", e)

    for window_index, window in enumerate(evidence["windows"]):
        for ordinal, sample in enumerate(window["samples"]):
            # A sample can appear in overlapping windows. This identity is
            # intentionally scoped to the query window and ordinal.
            o = (_uri("run", run, "signal", signal, "observation", sample["observationFingerprint"])\n                 if sample.get("observationFingerprint") else\n                 _uri("run", run, "window", window_index, "observation", ordinal))
            node(o, "VirtualObservation", source="TimescaleDB signal_samples",
                 identityScope=("CONTENT_FINGERPRINT_NOT_DATABASE_PRIMARY_KEY"\n                                if sample.get("observationFingerprint") else\n                                "QUERY_WINDOW_ORDINAL_NOT_DATABASE_PRIMARY_KEY"),
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
            "Virtual observation identifiers are query-window ordinals, not stable historian primary keys.",
            "GraphDB does not directly expose these observations via SPARQL.",
            "Engineering mapping is provisional; physical binding and shared run provenance are not verified.",
            "Recorded fault commands do not establish physical fault causation.",
        ],
    }


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
