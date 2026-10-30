"""SC-03 engineering/operational measurement-unit dimensional compatibility.

No unit is inferred from a signal name, BOM quantity, or descriptive text.
"""
from collections.abc import Mapping

# Explicitly supported unit symbols; scale is relative to canonical SI.
_UNITS = {
    "pa": ("pressure", 1.0), "kpa": ("pressure", 1000.0),
    "mpa": ("pressure", 1000000.0), "bar": ("pressure", 100000.0),
    "psi": ("pressure", 6894.757293168),
    "k": ("temperature", 1.0), "°c": ("temperature", 1.0),
    "degc": ("temperature", 1.0),
    "m": ("length", 1.0), "mm": ("length", 0.001),
}
# Offset is necessary for temperature conversion; compatibility does not
# imply that a pure multiplicative conversion is sufficient.
_OFFSETS = {"°c": 273.15, "degc": 273.15}


def evaluate_sc03(evidence):
    result = {"contract": "SC-03", "caseId": None, "status": "U",
              "engineeringCertification": "U", "authorization": False,
              "evidence": [], "reasons": [],
              "limitations": ["Assertion authority is not independently authenticated",
                              "SC-03 does not establish identity, quantity kind, or live binding"]}
    if not isinstance(evidence, Mapping):
        result["reasons"].append("Malformed evidence")
        return result
    result["caseId"] = evidence.get("caseId")
    revision, assertions = evidence.get("revision"), evidence.get("unitAssertions")
    if not isinstance(revision, str) or not revision.strip() or not isinstance(assertions, list):
        result["reasons"].append("Revision or unit assertions missing")
        return result
    selected = {}
    for side in ("engineering", "operational"):
        valid = [a for a in assertions if isinstance(a, Mapping)
                 and a.get("side") == side and isinstance(a.get("unit"), str)
                 and a["unit"].strip() and a.get("revision") == revision
                 and a.get("authority") == "AUTHENTICATED"
                 and isinstance(a.get("evidenceRef"), str) and a["evidenceRef"].strip()
                 and isinstance(a.get("provenance"), Mapping)
                 and a["provenance"].get("source")]
        result["evidence"].extend({"side": side, "unit": a["unit"],
                                   "evidenceRef": a["evidenceRef"],
                                   "provenance": dict(a["provenance"])} for a in valid)
        units = {a["unit"].strip().lower() for a in valid}
        if len(units) > 1:
            result["status"] = "F"
            result["reasons"].append("Conflicting authenticated " + side + " unit assertions")
        elif len(units) == 1:
            selected[side] = next(iter(units))
        else:
            result["reasons"].append("No authenticated revision-scoped " + side + " measurement unit")
    if result["status"] == "F" or len(selected) != 2:
        return result
    left, right = selected["engineering"], selected["operational"]
    if left not in _UNITS or right not in _UNITS:
        result["reasons"].append("Unit symbol not in explicit supported registry")
        return result
    ldim, lscale = _UNITS[left]
    rdim, rscale = _UNITS[right]
    if ldim != rdim:
        result["status"] = "F"
        result["reasons"].append("Measurement units have incompatible dimensions")
    else:
        result["status"] = "V"
        result["dimension"] = ldim
        result["conversion"] = {
            "from": left, "to": right,
            "scale": lscale / rscale,
            "offset": (_OFFSETS.get(left, 0.0) - _OFFSETS.get(right, 0.0)) / rscale,
            "formula": "target_value = source_value * scale + offset",
        }
    return result


def assess_graphdb_sc03(report):
    if not isinstance(report, dict) or report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB report")
    facts = report.get("facts")
    if not isinstance(facts, list):
        raise ValueError("Missing RDF facts")
    observations = []
    for row in facts:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str)
                                                for k in ("s", "p", "o", "g")):
            raise ValueError("Malformed RDF fact")
        if row["p"].rsplit("/", 1)[-1] == "hasUnit":
            observations.append({"subject": row["s"], "predicate": row["p"],
                                 "object": row["o"], "graph": row["g"],
                                 "classification": "BOM_ITEM_COUNT_NOT_MEASUREMENT_UNIT"
                                 if "engineeringbom/" in row["p"] and row["o"] == "EA"
                                 else "UNVERIFIED_UNIT_OBSERVATION"})
    return {"contract": "SC-03", "caseId": "SC03-T3", "status": "U",
            "engineeringCertification": "U", "authorization": False,
            "sourceStatus": report["status"], "sourceTruncated": report.get("truncated", True),
            "observedFacts": len(facts), "evidence": observations,
            "reasons": ["No authenticated revision-scoped engineering and operational measurement-unit pair",
                        "Engineering BOM EA denotes item count, not pressure measurement unit"],
            "limitations": ["Focused discovery cannot prove graph-wide absence",
                            "RDF provenance is not independently authenticated",
                            "SC-03 alone cannot authorize engineering use"]}
