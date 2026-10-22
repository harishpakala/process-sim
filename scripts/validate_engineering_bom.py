#!/usr/bin/env python3
"""Validate EBOM source identities and conservative asset/product associations."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((root/name).read_text(encoding="utf-8"))
bom=load("examples/aas/tep_engineering_bom_instance.json")
dex=load("examples/aas/tep_dexpi_instance.json")
ecad=load("examples/aas/tep_ecad_instance.json")
inventory=load("examples/aas/asset_inventory_instance.json")
def props(item):
    return {p["idShort"]:p["value"] for p in item["value"] if p["modelType"]=="Property"}
sources={}
for domain,model,groups in [("DEXPI",dex,("Equipments","InstrumentationFunctions","ActuatingFunctions")),("ECAD",ecad,("Devices",))]:
    for group in model["submodelElements"]:
        if group["idShort"] not in groups:continue
        for item in group["value"]:
            fields=props(item)
            key=(domain,fields["AssetIdentifier"])
            assert key not in sources,key
            sources[key]=(group["idShort"],item["idShort"],fields["LocalId"])
assets={p["EngineeringReference"]:p for p in map(props,inventory["submodelElements"][0]["value"]) if p.get("EngineeringReference")}
items=bom["submodelElements"][0]["value"]
assert len(items)==len(sources)==79
seen=set()
for item in items:
    p=props(item)
    key=(p["SourceDomain"],p["EngineeringReference"])
    assert key in sources and key not in seen,key
    seen.add(key)
    assert (p["SourceGroup"],p["ItemDescription"],p["EngineeringLocalId"])==sources[key]
    assert p["Quantity"]=="1" and p["Unit"]=="EA"
    assert p["QuantityBasis"]=="ONE_MODELED_ENGINEERING_OBJECT_NOT_PROCUREMENT_QUANTITY"
    asset=assets.get(p["EngineeringReference"])
    assert p["AssetReference"]==(asset.get("AssetId","") if asset else "")
    assert p["CandidateProductReference"]==(asset.get("CandidateProductReference","") if asset else "")
    assert p["ValidationStatus"]==("ASSET_REFERENCE_EXACT_MATCH" if asset else "UNRESOLVED_ASSET_REFERENCE")
    assert p["EquivalenceStatus"]=="NOT_ASSESSED_ACROSS_DOMAINS"
print(f"PASS: {len(items)} EBOM lines, {sum(bool(props(i)['AssetReference']) for i in items)} exact asset matches; no inferred cross-domain equivalence")
