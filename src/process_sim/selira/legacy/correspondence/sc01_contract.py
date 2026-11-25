"""SC-01 identity contract: auditable, three-valued correspondence evaluation.

Evidence is supplied by the caller. A declared 'verified' status is NOT
independent authentication; synthetic fixtures must never be used as live proof.
"""

# Created: 2026-10-30
# Author: Harish
from __future__ import annotations

from collections.abc import Mapping

ROLES = ("DEXPI", "ECAD", "PLC", "OPCUA", "TEP")
LINKS = tuple(zip(ROLES, ROLES[1:]))


def evaluate_sc01(evidence):
    """Evaluate explicit, reviewed identity assertions, failing closed.

    Input schema: {caseId, provenance, entities: {role: identifier},
    assertions: [{fromRole, toRole, fromId, toId, verdict, evidenceRef,
                  authority, provenance}]}. verdict is VERIFIED, CONTRADICTED,
    or UNKNOWN. Only authenticated, revision-scoped assertions can yield V/F.
    """
    result = {
        "contract": "SC-01", "caseId": None, "status": "U",
        "authorization": False, "evidence": [], "reasons": [],
        "limitations": ["Input assertions are not independently authenticated by this evaluator.",
                        "SC-01 status alone never authorizes engineering use."],
    }
    if not isinstance(evidence, Mapping):
        result["reasons"].append("Malformed evidence")
        return result
    result["caseId"] = evidence.get("caseId")
    entities = evidence.get("entities")
    assertions = evidence.get("assertions")
    if not isinstance(entities, Mapping) or not isinstance(assertions, list):
        result["reasons"].append("Missing entities or assertions")
        return result
    if any(not isinstance(entities.get(role), str) or not entities[role].strip()
           for role in ROLES):
        result["reasons"].append("Incomplete required entity identities")
        return result
    if not isinstance(evidence.get("revision"), str) or not evidence["revision"].strip():
        result["reasons"].append("Evidence revision missing")
        return result
    statuses = []
    for source, target in LINKS:
        matching = [a for a in assertions if isinstance(a, Mapping)
                    and a.get("fromRole") == source and a.get("toRole") == target]
        usable = []
        for a in matching:
            if (a.get("fromId") != entities[source]
                    or a.get("toId") != entities[target]):
                continue
            if (a.get("revision") != evidence["revision"]
                    or a.get("authority") != "AUTHENTICATED"
                    or not isinstance(a.get("evidenceRef"), str)
                    or not a["evidenceRef"].strip()
                    or not isinstance(a.get("provenance"), Mapping)
                    or not a["provenance"].get("source")):
                continue
            if a.get("verdict") in ("VERIFIED", "CONTRADICTED"):
                usable.append(a)
        verdicts = {a["verdict"] for a in usable}
        status = ("F" if "CONTRADICTED" in verdicts else
                  "V" if verdicts == {"VERIFIED"} else "U")
        statuses.append(status)
        result["evidence"].append({
            "link": source + "->" + target, "status": status,
            "references": [{"evidenceRef": a["evidenceRef"],
                            "provenance": dict(a["provenance"])} for a in usable],
        })
        if status != "V":
            result["reasons"].append(
                source + "->" + target + ": " +
                ("authoritative contradiction" if status == "F"
                 else "no authenticated revision-scoped correspondence"))
    result["status"] = ("F" if "F" in statuses else
                        "V" if all(s == "V" for s in statuses) else "U")
    return result
