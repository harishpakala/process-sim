"""SC-05 prototype: operational endpoint binding; no live OPC UA verification."""
from collections.abc import Mapping


def evaluate_sc05(data):
    result = {"contract": "SC-05", "status": "U", "authorization": False,
              "engineeringCertification": "U", "evidence": [], "reasons": [],
              "limitations": ["Caller assertions are not independently authenticated",
                              "No live OPC UA endpoint is contacted"]}
    if not isinstance(data, Mapping):
        result["reasons"].append("Missing binding evidence")
        return result
    target = data.get("target")
    assertions = data.get("bindingAssertions")
    if not isinstance(target, Mapping) or not isinstance(assertions, list) or not all(
            isinstance(target.get(k), str) and target[k].strip()
            for k in ("signal", "nodeId", "revision")):
        result["reasons"].append("Incomplete target or assertions")
        return result
    usable = [a for a in assertions if isinstance(a, Mapping)
              and all(a.get(k) == target[k] for k in ("signal", "nodeId", "revision"))
              and a.get("authority") == "AUTHENTICATED"
              and a.get("verdict") in ("BOUND", "CONTRADICTED")
              and isinstance(a.get("evidenceRef"), str) and a["evidenceRef"].strip()
              and isinstance(a.get("provenance"), Mapping) and a["provenance"].get("source")]
    result["evidence"] = [dict(a) for a in usable]
    verdicts = {a["verdict"] for a in usable}
    result["status"] = ("F" if "CONTRADICTED" in verdicts else
                        "V" if verdicts == {"BOUND"} else "U")
    if result["status"] == "U":
        result["reasons"].append("No authenticated revision-scoped operational binding")
    return result


def assess_graphdb_sc05(report):
    if not isinstance(report, dict) or report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB discovery report")
    facts = report.get("facts")
    if not isinstance(facts, list):
        raise ValueError("Missing facts")
    names = {"hasOPCUANodeId", "hasMappingStatus", "hasMappingBasis",
             "hasSignalName", "hasSimulationStatus"}
    evidence = []
    for row in facts:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("s","p","o","g")):
            raise ValueError("Malformed RDF observation")
        if row["p"].rsplit("/",1)[-1] in names:
            evidence.append({"subject": row["s"], "predicate": row["p"],
                             "object": row["o"], "graph": row["g"],
                             "classification": "DECLARED_NOT_LIVE_VERIFIED"})
    return {"contract": "SC-05", "status": "U", "authorization": False,
            "engineeringCertification": "U", "sourceStatus": report["status"],
            "sourceTruncated": report.get("truncated", True),
            "observedFacts": len(facts), "evidence": evidence,
            "reasons": ["Declared OPC UA mapping is not authenticated live binding"],
            "limitations": ["Focused query cannot prove graph-wide absence",
                            "No live OPC UA connection or endpoint verification performed"]}
