"""README-proposed consumer acceptance contracts.

Consumer fitness is distinct from source engineering qualification.
Assertions marked AUTHENTICATED are not independently authenticated here.
"""
from collections.abc import Mapping

REQUIREMENTS = {
    "CAC-01": ("runId", "timeInterval", "units", "provenance", "measurementCoverage"),
    "CAC-02": ("approval", "targetProperty", "units", "configuration"),
}


def evaluate_cac(contract, data, source_status="U"):
    if contract not in REQUIREMENTS:
        raise ValueError("Unknown CAC contract")
    result = {"contract": contract, "status": "U", "consumerAcceptance": False,
              "authorization": False, "sourceQualification": source_status,
              "evidence": [], "reasons": [],
              "limitations": ["Evidence assertions are not independently authenticated",
                              "Consumer fitness cannot override source qualification"]}
    if not isinstance(data, Mapping):
        result["reasons"].append("Consumer task missing")
        return result
    if data.get("inScope") is False:
        result["status"] = "NA"
        result["reasons"].append("Explicitly outside this consumer task scope")
        return result
    if data.get("inScope") is not True:
        result["reasons"].append("Consumer task scope unresolved")
        return result
    requirements = data.get("requirements")
    checks = data.get("checks")
    if not isinstance(requirements, Mapping) or not isinstance(checks, list):
        result["reasons"].append("Requirements or checks missing")
        return result
    statuses = []
    for key in REQUIREMENTS[contract]:
        required = requirements.get(key)
        if required is None or required == "":
            statuses.append("U")
            result["reasons"].append("Missing requirement: " + key)
            continue
        usable = [c for c in checks if isinstance(c, Mapping)
                  and c.get("requirement") == key and c.get("expected") == required
                  and c.get("authority") == "AUTHENTICATED"
                  and c.get("verdict") in ("MET", "VIOLATED")
                  and isinstance(c.get("evidenceRef"), str) and c["evidenceRef"].strip()
                  and isinstance(c.get("provenance"), Mapping) and c["provenance"].get("source")]
        result["evidence"].extend(dict(c) for c in usable)
        verdicts = {c["verdict"] for c in usable}
        statuses.append("F" if "VIOLATED" in verdicts else
                        "V" if verdicts == {"MET"} else "U")
    result["status"] = ("F" if "F" in statuses else
                        "V" if statuses and all(s == "V" for s in statuses) else "U")
    if result["status"] == "U":
        result["reasons"].append("Task fitness evidence incomplete")
    if source_status != "V":
        result["reasons"].append("Source engineering qualification not verified")
    # Even a synthetic V+V is not production authorization.
    return result
