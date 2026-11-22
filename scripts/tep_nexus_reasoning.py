"""Deterministic, read-only reasoning over one query-scoped VTKG snapshot.

No database access, no physical sensor identity inference, and no causal claims.
"""
from collections import defaultdict


def reason(graph, *, domain, engineering_function, run_id, expected_count):
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    for e in edges:
        if e["source"] not in nodes or e["target"] not in nodes:
            raise ValueError("Graph edge references missing node")
        outgoing[(e["source"], e["predicate"])].append(e["target"])
        incoming[(e["target"], e["predicate"])].append(e["source"])

    def one(items, description):
        if len(items) != 1:
            raise ValueError(f"Expected one {description}, found {len(items)}")
        return items[0]

    function = one([n for n in nodes.values() if n["type"] == "EngineeringFunction"
                    and n.get("domain") == domain and n.get("localId") == engineering_function],
                   "selected engineering function")
    run = one([n for n in nodes.values() if n["type"] == "SimulationRun"
               and n.get("runId") == run_id], "selected run")
    signal_id = one(outgoing[(function["id"], "mapsToSignal")], "mapped signal")
    signal = nodes[signal_id]
    if signal["type"] != "OperationalSignal" or signal_id not in outgoing[(run["id"], "hasSignal")]:
        raise ValueError("Selected function signal not associated with run")
    observation_ids = set(incoming[(signal_id, "observesSignal")]) & set(incoming[(run["id"], "belongsToRun")])
    observations = [nodes[i] for i in observation_ids]
    if any(n["type"] != "VirtualObservation" for n in observations):
        raise ValueError("Non-observation linked through observation edges")
    observations.sort(key=lambda n: (n.get("simulationTimeHours", 0), n.get("observedAt", ""), n["id"]))
    if len(observations) != expected_count:
        raise ValueError("R01 graph traversal count differs from historian response")
    asset_ids = outgoing[(function["id"], "hasAssetIdentifier")] + outgoing[(function["id"], "associatedWithAsset")]
    if len(asset_ids) != 1:
        raise ValueError("Selected engineering function must have one asset reference")
    asset = nodes[asset_ids[0]]
    r01 = {
        "status": "complete", "function": {"id": function["id"], "domain": domain, "localId": engineering_function},
        "signal": {"id": signal_id, "signalId": signal.get("signalId")},
        "run": {"id": run["id"], "runId": run_id},
        "asset": {"id": asset["id"], "type": asset["type"],
                  "identifier": asset.get("identifier", asset["id"])},
        "path": [
            {"source": function["id"], "predicate": "mapsToSignal", "target": signal_id},
            {"source": run["id"], "predicate": "hasSignal", "target": signal_id},
            {"source": function["id"], "predicate": "hasAssetIdentifier" if asset["type"] == "AssetIdentifier" else "associatedWithAsset", "target": asset["id"]},
        ],
        "observationCount": len(observations),
        "observations": [{"id": n["id"], "simulationTimeHours": n.get("simulationTimeHours"),
                          "value": n.get("value"), "observedAt": n.get("observedAt"),
                          "contentFingerprint": n.get("contentFingerprint"),
                          "path": [
                              {"source": n["id"], "predicate": "observesSignal", "target": signal_id},
                              {"source": n["id"], "predicate": "belongsToRun", "target": run["id"]},
                          ]} for n in observations],
        "provenance": {"engineeringMapping": "GraphDB", "observations": "TimescaleDB signal_samples",
                       "physicalSensorBinding": "NOT_VERIFIED", "materializedInGraphDB": False},
    }
    # Reverse traceability is bounded to this snapshot and the same operational signal.
    associated_functions = []
    for function_id in sorted(set(incoming[(signal_id, "mapsToSignal")])):
        n = nodes[function_id]
        if n["type"] != "EngineeringFunction":
            raise ValueError("Invalid engineering mapping edge")
        associated_functions.append({
            "id": n["id"], "domain": n.get("domain"), "localId": n.get("localId"),
            "path": [{"source": n["id"], "predicate": "mapsToSignal", "target": signal_id}],
        })
    r02 = {"status": "complete", "signalId": signal_id, "observationCount": len(observations),
           "engineeringFunctions": associated_functions,
           "scope": "Reverse association within the retrieved snapshot; no new historian retrieval"}
    domains = {n["domain"] for n in associated_functions if n["domain"] in ("DEXPI", "ECAD")}
    r03 = {"status": "complete" if domains == {"DEXPI", "ECAD"} else "insufficient_evidence",
           "sharedSignal": signal.get("signalId"), "engineeringFunctions": associated_functions,
           "domainsPresent": sorted(domains),
           "interpretation": "Shared operational signal identifier; physical sensor identity NOT_VERIFIED"}
    # Only commands explicitly connected to this run are eligible. A recorded
    # command is an event marker, never proof that a fault physically occurred.
    command_ids = outgoing[(run["id"], "hasRecordedCommand")]
    commands = []
    for command_id in command_ids:
        command = nodes[command_id]
        if command["type"] != "RecordedFaultCommand":
            raise ValueError("Run command edge does not reference a recorded command")
        t = command.get("simulationTimeHours")
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not __import__("math").isfinite(t):
            raise ValueError("Recorded command has invalid simulation time")
        commands.append(command)
    commands.sort(key=lambda n: (n["simulationTimeHours"], str(n.get("eventId", ""))))
    if not commands:
        r04 = {"status": "insufficient_evidence",
               "reason": "No run-linked RecordedFaultCommand nodes in this historian snapshot",
               "events": [], "interpretation": "No temporal comparison or fault causation inferred"}
    else:
        events = []
        for command in commands:
            t = command["simulationTimeHours"]
            before = [n for n in observations if n.get("simulationTimeHours") is not None
                      and n["simulationTimeHours"] < t]
            after = [n for n in observations if n.get("simulationTimeHours") is not None
                     and n["simulationTimeHours"] > t]
            at = [n for n in observations if n.get("simulationTimeHours") == t]
            events.append({
                "eventId": command.get("eventId"), "action": command.get("action"),
                "simulationTimeHours": t, "observedAt": command.get("observedAt"),
                "commandNodeId": command["id"],
                "path": {"source": run["id"], "predicate": "hasRecordedCommand", "target": command["id"]},
                "beforeCount": len(before), "atCount": len(at), "afterCount": len(after),
                "beforeObservationIds": [n["id"] for n in before],
                "afterObservationIds": [n["id"] for n in after],
                "beforeMean": sum(n["value"] for n in before) / len(before) if before else None,
                "afterMean": sum(n["value"] for n in after) / len(after) if after else None,
            })
        comparable = any(e["beforeCount"] and e["afterCount"] for e in events)
        r04 = {"status": "complete" if comparable else "insufficient_evidence",
               "reason": "Recorded event markers lack observations on both sides" if not comparable else "",
               "events": events,
               "interpretation": "Descriptive before/after association only; no causal attribution or verified physical fault state"}
    if r03["status"] == "complete" and r04["status"] == "complete":
        r05 = {"status": "complete", "sharedSignal": signal.get("signalId"),
               "engineeringFunctions": associated_functions, "temporalEvents": r04["events"],
               "interpretation": "Cross-domain shared-signal association with recorded-command temporal comparison; not proof of causation"}
    else:
        r05 = {"status": "insufficient_evidence",
               "reason": "Requires both DEXPI and ECAD mappings plus a run-linked command with before/after observations"}
    return {"R01": r01, "R02": r02, "R03": r03, "R04": r04, "R05": r05}
