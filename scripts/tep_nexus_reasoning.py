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
    return {"R01": r01, "R02": r02, "R03": r03,
            "R04": {"status": "not_implemented", "reason": "No recorded command temporal evidence"},
            "R05": {"status": "not_implemented", "reason": "Combined cross-domain temporal operator not implemented"}}
