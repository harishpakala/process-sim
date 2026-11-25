"""Aggregate SC and task-specific CAC verdicts, without granting authorization."""

# Created: 2026-10-30
# Author: Harish

SC_IDS = ("SC-01", "SC-02", "SC-03", "SC-04", "SC-05")
CAC_IDS = ("CAC-01", "CAC-02")


def conjunction(statuses):
    values = list(statuses)
    if not values or any(s not in ("V", "F", "U") for s in values):
        return "U"
    if "F" in values:
        return "F"
    return "V" if all(s == "V" for s in values) else "U"


def aggregate(results):
    by_id = {r["contract"]: r for r in results}
    if len(by_id) != len(results):
        raise ValueError("Duplicate contract results")
    missing = [name for name in SC_IDS + CAC_IDS if name not in by_id]
    if missing:
        raise ValueError("Missing contract results: " + ", ".join(missing))
    source = conjunction(by_id[name]["status"] for name in SC_IDS)
    consumers = {}
    for name in CAC_IDS:
        fitness = by_id[name]["status"]
        consumers[name] = {
            "fitness": fitness,
            "decision": ("NA" if fitness == "NA" else
                         "F" if source == "F" or fitness == "F" else
                         "V" if source == "V" and fitness == "V" else "U"),
            "accepted": False,
            "authorization": False,
        }
    return {"sourceQualification": source, "consumers": consumers,
            "engineeringCertification": "U", "authorization": False,
            "limitations": ["V is evaluator-level only; external evidence authentication and approval not established",
                            "NA is consumer-task scope only, never a substitute for verified source evidence"]}
