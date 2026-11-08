#!/usr/bin/env python3
"""Validate registry links and candidate-only semantics."""

# Created: 2026-10-23
# Author: Harish
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"examples"/"aas"
def load(name):
    return json.loads((root/name).read_text(encoding="utf-8"))
registry=load("tep_engineering_relationship_registry.json")["relationships"]
pairs=load("tep_dexpi_ecad_reconciliation.json")["candidates"]
bom=load("tep_engineering_bom_instance.json")
def props(item):
    return {p["idShort"]:p["value"] for p in item["value"] if p["modelType"]=="Property"}
references={(p["SourceDomain"],p["EngineeringReference"]) for item in bom["submodelElements"][1]["value"] for p in [props(item)]}
assert len(registry)==len(pairs)==29
assert len({r["relationshipId"] for r in registry})==len(registry)
assert len({(r["sourceReference"],r["targetReference"]) for r in registry})==len(registry)
for r,p in zip(registry,pairs):
    assert r["sourceReference"]==p["dexpiReference"]
    assert r["targetReference"]==p["ecadReference"]
    assert r["scopeAssembly"]==p["equipmentAssembly"]
    assert r["sourceDomain"]=="DEXPI" and r["targetDomain"]=="ECAD"
    assert ("DEXPI",r["sourceReference"]) in references
    assert ("ECAD",r["targetReference"]) in references
    assert r["relationshipType"]=="CANDIDATE_FUNCTION_DEVICE_CORRESPONDENCE"
    assert r["verificationStatus"]=="PENDING_REVIEW"
    assert r["physicalMembershipVerified"] is False and r["identityVerified"] is False
print(f"PASS: {len(registry)} typed candidate relationships; no identity or physical-membership approvals")
