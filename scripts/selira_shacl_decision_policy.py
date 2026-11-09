#!/usr/bin/env python3
"""Independent SHACL-style three-valued decision comparator.

This is a Python interpretation of an RDF/SHACL validation report, not
an execution of SHACL-SPARQL itself. See comparison limitations.
"""

# Created: 2026-10-30
# Author: Harish
from itertools import product

SC = ("SC-01", "SC-02", "SC-03", "SC-04", "SC-05")
CAC = ("CAC-01", "CAC-02")


def derive_source(contract_findings):
    """F = explicit contradiction; U = absent/inconclusive; V = all verified."""
    if set(contract_findings) != set(SC):
        raise ValueError("Exactly five SC findings required")
    if any(contract_findings[key] == "contradiction" for key in SC):
        return "F"
    if all(contract_findings[key] == "verified" for key in SC):
        return "V"
    return "U"


def derive_consumer(check_findings, in_scope=True):
    if not in_scope:
        return "NA"
    if any(value == "contradiction" for value in check_findings.values()):
        return "F"
    if check_findings and all(value == "verified" for value in check_findings.values()):
        return "V"
    return "U"


def compose(source, fitness):
    if fitness == "NA":
        return "NA"
    if source == "F" or fitness == "F":
        return "F"
    if source == "V" and fitness == "V":
        return "V"
    return "U"


def compare(findings):
    """Findings must be extracted independently from evidence, not SELiRA output."""
    source = derive_source(findings["source"])
    consumers = {}
    for name in CAC:
        item = findings["consumers"][name]
        fitness = derive_consumer(item["checks"], item.get("inScope", True))
        consumers[name] = {"fitness": fitness, "decision": compose(source, fitness)}
    return {"source": source, "consumers": consumers,
            "engineeringAuthorization": False}
