#!/usr/bin/env python3
"""Validate EBOM source identities and conservative asset/product associations."""

# Created: 2026-10-22
# Author: Harish
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
assets={p["AssetIdentifier"]:p for p in map(props,inventory["submodelElements"][0]["value"]) if p.get("AssetIdentifier")}
catalog=load("examples/aas/product_catalog_instance.json")
product_ids={p["ProductIdentifier"] for p in map(props,catalog["submodelElements"][0]["value"]) if p.get("ProductIdentifier")}
assemblies=bom["submodelElements"][0]["value"]
items=bom["submodelElements"][1]["value"]
assembly_map={props(a)["BOMItemId"]:props(a) for a in assemblies}
assert len(assembly_map)==len(assemblies)==22
for parent in ("ASM-REACTOR","ASM-CONDENSER","ASM-SEPARATOR","ASM-COMPRESSOR","ASM-STRIPPER"):
    assert {a for a,p in assembly_map.items() if p["ParentItemId"]==parent and p["AssemblyKind"]=="DISCIPLINE_PLACEHOLDER"}=={parent+"-"+suffix for suffix in ("MECH","INST","CTRL")}
assert assembly_map["ASM-ROOT"]["ParentItemId"]==""
for aid, assembly in assembly_map.items():
    if aid!="ASM-ROOT":assert assembly["ParentItemId"] in assembly_map
    assert assembly["ItemType"]=="ASSEMBLY"
    if assembly["AssemblyKind"]=="DISCIPLINE_PLACEHOLDER":
        assert assembly["StructureStatus"]=="PLACEHOLDER_NO_VERIFIED_COMPONENTS_OR_QUANTITY"
        assert assembly["QuantityPerAssembly"]==""
        assert assembly["ParentItemId"] in {"ASM-REACTOR","ASM-CONDENSER","ASM-SEPARATOR","ASM-COMPRESSOR","ASM-STRIPPER"}
    else:
        assert assembly["StructureStatus"]=="PROVISIONAL_EQUIPMENT_ASSEMBLY_NO_VERIFIED_COMPONENT_BREAKDOWN"
equipment_parents={"R-001":"ASM-REACTOR","C-001":"ASM-CONDENSER","V-001":"ASM-SEPARATOR","K-001":"ASM-COMPRESSOR","S-001":"ASM-STRIPPER"}
assert len(items)==len(sources)==79
seen=set()
for item in items:
    p=props(item)
    key=(p["SourceDomain"],p["EngineeringReference"])
    assert key in sources and key not in seen,key
    seen.add(key)
    assert (p["SourceGroup"],p["ItemDescription"],p["EngineeringLocalId"])==sources[key]
    assert p["Quantity"]=="1" and p["Unit"]=="EA"
    parent=equipment_parents.get(p["EngineeringLocalId"]) if p["SourceDomain"]=="DEXPI" and p["SourceGroup"]=="Equipments" else None
    assert p["ParentItemId"]==(parent or "ASM-UNASSIGNED")
    assert p["ItemType"]=="ENGINEERING_OBJECT" and p["QuantityPerAssembly"]=="1"
    assert p["FunctionalAssemblyReference"] in ("","ASM-REACTOR","ASM-SEPARATOR","ASM-STRIPPER","ASM-CONDENSER","ASM-COMPRESSOR")
    assert p["AssociationBasis"]==("SOURCE_NAME_OR_DESCRIPTION_FUNCTIONAL_ASSOCIATION_NOT_PHYSICAL_MEMBERSHIP" if p["FunctionalAssemblyReference"] else "UNRESOLVED")
    if p["FunctionalAssemblyReference"]:
        assert p["ParentItemId"]=="ASM-UNASSIGNED", "Functional association must not assert physical membership"
    assert p["BOMPosition"]==p["BOMItemId"]
    assert p["StructureStatus"]==("EQUIPMENT_OBJECT_UNDER_NAMED_ASSEMBLY_COMPONENT_BREAKDOWN_UNVERIFIED" if parent else "UNASSIGNED_NO_VERIFIED_EQUIPMENT_MEMBERSHIP")
    assert p["QuantityBasis"]=="ONE_MODELED_ENGINEERING_OBJECT_NOT_PROCUREMENT_QUANTITY"
    asset=assets.get(p["AssetIdentifier"])
    assert "AssetReference" not in p and "CandidateProductReference" not in p
    product=(asset.get("ProductIdentifier") or asset.get("CandidateProductReference") or "") if asset else ""
    assert p["ProductIdentifier"]==(product if product in product_ids else "")
    assert not p["ProductIdentifier"] or p["ProductIdentifier"] in product_ids
    assert p["ValidationStatus"]==("ASSET_IDENTIFIER_EXACT_MATCH" if asset else "ASSET_INVENTORY_MATCH_UNRESOLVED")
    assert p["EquivalenceStatus"]=="NOT_ASSESSED_ACROSS_DOMAINS"
print(f"PASS: {len(items)} EBOM lines, {sum(props(i)['ValidationStatus']=='ASSET_IDENTIFIER_EXACT_MATCH' for i in items)} exact asset identifiers, {sum(bool(props(i)['ProductIdentifier']) for i in items)} catalog product identifiers; no inferred physical installation")
