"""Classify SC-01 GraphDB observations without upgrading discovery to certification."""
from __future__ import annotations

from collections import defaultdict

LINKS = ("DEXPI->ECAD", "ECAD->PLC", "PLC->OPCUA", "OPCUA->TEP")


def assess_graphdb_sc01(report):
    if not isinstance(report, dict) or report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB report")
    facts = report.get("facts")
    if not isinstance(facts, list):
        raise ValueError("Missing RDF facts")
    grouped = defaultdict(list)
    for row in facts:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str)
                                                for k in ("s", "p", "o", "g")):
            raise ValueError("Invalid RDF fact")
        grouped[row["p"].rsplit("/", 1)[-1]].append(row)

    def references(*names, value=None):
        rows = [r for name in names for r in grouped[name]
                if value is None or r["o"] == value]
        return [{"subject": r["s"], "predicate": r["p"], "object": r["o"],
                 "graph": r["g"]} for r in rows]

    evidence = [
        {"link": "DEXPI->ECAD", "classification": "UNRESOLVED",
         "observations": references("hasEquivalenceStatus", value="NOT_ASSESSED_ACROSS_DOMAINS")
         + references("hasMeasuredVariable", value="")},
        {"link": "ECAD->PLC", "classification": "EXPLICIT_GRAPH_RELATIONSHIP",
         "observations": references("isConnectedTo")
         + references("hasAddress", value="I10.19")},
        {"link": "PLC->OPCUA", "classification": "DECLARED_IDENTIFIER_ASSOCIATION",
         "observations": references("hasPLCMapping", value="I10.19")
         + references("hasOperationalReference", value="XMEAS7")},
        {"link": "OPCUA->TEP", "classification": "PROVISIONAL_MAPPING",
         "observations": references("hasMappingStatus", value="PROVISIONAL_ENGINEERING_MATCH")
         + references("hasMappingBasis")
         + references("hasOPCUANodeId")
         + references("hasSignalName", value="XMEAS7")},
    ]
    # The classifications describe observed records, not authenticated links.
    for item in evidence:
        if not item["observations"]:
            item["classification"] = "NOT_OBSERVED"
        item["status"] = "U"
    return {
        "contract": "SC-01", "caseId": "SC01-T3", "status": "U",
        "engineeringCertification": "U", "authorization": False,
        "sourceStatus": report["status"], "sourceTruncated": report.get("truncated", True),
        "observedFacts": len(facts), "evidence": evidence,
        "reasons": [
            "No authenticated, revision-scoped cross-domain identity chain established",
            "Explicit ECAD wiring and identifier declarations are discovery evidence, not certified equivalence",
            "OPC UA mapping remains provisional and live binding is unverified",
        ],
        "limitations": [
            "Predicate-specific classification does not establish graph-wide absence",
            "GraphDB RDF facts are not independently authenticated by this evaluator",
            "SC-01 cannot authorize engineering use without other contracts",
        ],
    }
