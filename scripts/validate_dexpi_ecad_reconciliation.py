#!/usr/bin/env python3
"""Validate candidate DEXPI–ECAD correspondences without asserting equivalence."""

# Created: 2026-10-22
# Author: Harish
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((root / "examples/aas" / name).read_text(encoding="utf-8"))
def fields(obj):
    return {p["idShort"]: p["value"] for p in obj["value"] if p["modelType"] == "Property"}

dex = load("tep_dexpi_instance.json")
ecad = load("tep_ecad_instance.json")
bom = load("tep_engineering_bom_instance.json")
crosswalk = load("tep_dexpi_ecad_reconciliation.json")
dex_sources = {o["idShort"]: fields(o) for g in dex["submodelElements"] if g["idShort"] in ("InstrumentationFunctions", "ActuatingFunctions") for o in g["value"]}
ecad_sources = {o["idShort"]: fields(o) for g in ecad["submodelElements"] if g["idShort"] == "Devices" for o in g["value"]}
bom_items = { (p["SourceDomain"], p["EngineeringReference"]): p for o in bom["submodelElements"][1]["value"] for p in [fields(o)] }
seen_dex, seen_ecad = set(), set()
for row in crosswalk["candidates"]:
    d, e = row["dexpiIdShort"], row["ecadIdShort"]
    assert d in dex_sources and e in ecad_sources, (d, e)
    assert d not in seen_dex and e not in seen_ecad, (d, e)
    seen_dex.add(d); seen_ecad.add(e)
    assert row["dexpiLocalId"] == dex_sources[d]["LocalId"]
    assert row["dexpiReference"] == dex_sources[d]["AssetIdentifier"]
    assert row["ecadLocalId"] == ecad_sources[e]["LocalId"]
    assert row["ecadReference"] == ecad_sources[e]["AssetIdentifier"]
    assert row["ecadDescription"] == ecad_sources[e].get("Description", "")
    assert row["status"] == "CANDIDATE_NOT_VERIFIED" and row["identityConfirmed"] is False
    assert row["equipmentAssembly"] in ("ASM-REACTOR","ASM-SEPARATOR","ASM-STRIPPER","ASM-CONDENSER","ASM-COMPRESSOR","ASM-ROOT")
    for domain, ref in (("DEXPI",row["dexpiReference"]),("ECAD",row["ecadReference"])):
        assert (domain, ref) in bom_items
        assert bom_items[(domain, ref)]["EquivalenceStatus"] == "NOT_ASSESSED_ACROSS_DOMAINS"
print(f"PASS: {len(seen_dex)} candidate pairs, all source references valid, no verified identity claims")
