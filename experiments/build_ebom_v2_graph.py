#!/usr/bin/env python3
"""Build an additive, evidence-preserving EBOM V2 RDF overlay from AAS instance JSON.

No changes to V1. Does not assert physical membership from functional associations.
Usage: python experiments/build_ebom_v2_graph.py
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

CORE = Namespace("https://example.org/dtwise/core/")
EBOM = Namespace("https://example.org/engineeringbom/")
BASE = "https://example.org/dtwise/ebom-v2/"
DEFAULT_INPUT = Path("semantic/instances/tep/tep_engineering_bom_instance.json")
DEFAULT_OUTPUT = Path("semantic/derived/tep_ebom_v2.ttl")
UNKNOWN = {"", "UNSPECIFIED", "UNRESOLVED", "UNKNOWN", "NONE", "NULL"}

def records(doc, group):
    groups = [x for x in doc["submodelElements"] if x.get("idShort") == group]
    if len(groups) != 1:
        raise ValueError(f"Expected one {group} collection")
    for node in groups[0]["value"]:
        yield {p["idShort"]: str(p.get("value", "")) for p in node["value"]
               if p.get("modelType") == "Property"}

def uri(kind, identifier):
    return URIRef(BASE + kind + "/" + quote(identifier, safe=""))

def add_literal(graph, subject, predicate, value):
    if value is not None and str(value).strip():
        graph.add((subject, predicate, Literal(str(value))))

def build(doc):
    g = Graph()
    g.bind("core", CORE)
    g.bind("ebom", EBOM)
    g.bind("rdfs", RDFS)
    assemblies = list(records(doc, "Assemblies"))
    items = list(records(doc, "BOMItems"))
    all_records = [("assembly", a) for a in assemblies] + [("item", i) for i in items]
    ids = [r["BOMItemId"] for _, r in all_records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate BOMItemId in EBOM input")
    known = {r["BOMItemId"]: uri(kind, r["BOMItemId"]) for kind, r in all_records}
    assembly_ids = {a["BOMItemId"] for a in assemblies}
    for kind, row in all_records:
        ident = row["BOMItemId"]
        node = known[ident]
        g.add((node, RDF.type, CORE.AssemblyRecord if kind == "assembly" else CORE.BOMItemRecord))
        add_literal(g, node, EBOM.hasBOMItemId, ident)
        for key in ("EngineeringLocalId", "ItemDescription", "AssetIdentifier",
                    "ProductIdentifier", "SourceDomain", "SourceGroup", "StructureStatus",
                    "Revision", "QuantityBasis", "AssociationBasis"):
            add_literal(g, node, EBOM["has" + key], row.get(key))
        add_literal(g, node, RDFS.label, row.get("ItemDescription") or ident)
        parent = row.get("ParentItemId", "").strip()
        if parent and parent in known:
            relation = uri("parent-reference", ident)
            g.add((relation, RDF.type, CORE.ParentReference))
            g.add((relation, CORE.referenceSource, node))
            g.add((relation, CORE.referenceTarget, known[parent]))
            add_literal(g, relation, CORE.sourceField, "ParentItemId")
            add_literal(g, relation, CORE.structureStatus, row.get("StructureStatus"))
            add_literal(g, relation, CORE.sourceRecordId, ident)
            # This is a recorded parent reference, NOT a verified BOM occurrence.
            g.add((node, CORE.hasRecordedParent, known[parent]))
        elif parent and parent not in UNKNOWN:
            raise ValueError(f"Dangling ParentItemId {parent} for {ident}")
        target = row.get("FunctionalAssemblyReference", "").strip()
        if target:
            if target not in assembly_ids:
                raise ValueError(f"Dangling functional assembly {target} for {ident}")
            assoc = uri("functional-association", ident)
            g.add((assoc, RDF.type, CORE.FunctionalAssociation))
            g.add((assoc, CORE.functionalAssociationSource, node))
            g.add((assoc, CORE.functionalAssociationTarget, known[target]))
            add_literal(g, assoc, CORE.associationBasis, row.get("AssociationBasis"))
            add_literal(g, assoc, CORE.structureStatus, row.get("StructureStatus"))
            add_literal(g, assoc, CORE.sourceRecordId, ident)
            add_literal(g, assoc, CORE.sourceField, "FunctionalAssemblyReference")
            # Never materialize a physical membership / BOM occurrence from this.
            g.add((node, CORE.functionallyAssociatedWith, known[target]))
    # Ground equipment IDs to assembly contexts via recorded parent references.
    # No substring matching, benchmark alias, or physical component inference.
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    g = build(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(args.output), format="turtle")
    print(f"Wrote {len(g)} triples to {args.output}")

if __name__ == "__main__":
    main()
