#!/usr/bin/env python3
"""Validate EBOM V2 overlay and multiple traversals; no GraphDB credentials required.

python experiments/validate_ebom_v2_graph.py
python experiments/validate_ebom_v2_graph.py --shacl  # requires pyshacl
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from rdflib import Graph, Literal, Namespace, RDF, URIRef

CORE = Namespace("https://example.org/dtwise/core/")
EBOM = Namespace("https://example.org/engineeringbom/")
ROOT = Path(__file__).resolve().parents[1]

def records(doc, group):
    group_node = next(x for x in doc["submodelElements"] if x["idShort"] == group)
    return [{p["idShort"]: str(p.get("value", "")) for p in n["value"]
             if p.get("modelType") == "Property"} for n in group_node["value"]]

def validate(g, doc):
    assemblies = records(doc, "Assemblies")
    items = records(doc, "BOMItems")
    by_id = {r["BOMItemId"]: r for r in assemblies + items}
    if len(by_id) != len(assemblies) + len(items):
        raise AssertionError("Duplicate source record IDs")
    source_associations = [r for r in items if r.get("FunctionalAssemblyReference")]
    rdf_associations = list(g.subjects(RDF.type, CORE.FunctionalAssociation))
    parent_refs = list(g.subjects(RDF.type, CORE.ParentReference))
    expected_parents = sum(bool(r.get("ParentItemId")) for r in assemblies + items)
    assert len(rdf_associations) == len(source_associations), "Functional association count mismatch"
    assert len(parent_refs) == expected_parents, "Recorded parent reference count mismatch"
    assert not list(g.subjects(RDF.type, CORE.BOMOccurrence)), "Unexpected BOM occurrences"
    assert not list(g.triples((None, CORE.hasBOMOccurrence, None))), "Unexpected structural BOM edge"
    for a in rdf_associations:
        sources = list(g.objects(a, CORE.functionalAssociationSource))
        targets = list(g.objects(a, CORE.functionalAssociationTarget))
        assert len(sources) == len(targets) == 1, "Missing or ambiguous association endpoints"
        assert (targets[0], RDF.type, CORE.AssemblyRecord) in g
        assert len(list(g.objects(a, CORE.sourceRecordId))) == 1
        assert len(list(g.objects(a, CORE.associationBasis))) == 1
        assert (sources[0], CORE.functionallyAssociatedWith, targets[0]) in g
    for p in parent_refs:
        sources = list(g.objects(p, CORE.referenceSource))
        targets = list(g.objects(p, CORE.referenceTarget))
        assert len(sources) == len(targets) == 1
        assert (sources[0], CORE.hasRecordedParent, targets[0]) in g
    # Parent-reference cycles are invalid even when physical composition is not asserted.
    parent = {r["BOMItemId"]: r.get("ParentItemId") for r in assemblies + items}
    for start in parent:
        seen = set()
        node = start
        while node and node in parent:
            if node in seen:
                raise AssertionError(f"Cycle in parent references at {node}")
            seen.add(node)
            node = parent[node]
    reactor_nodes = list(g.subjects(EBOM.hasEngineeringLocalId, Literal("R-001")))
    assert len(reactor_nodes) == 1, "R-001 should resolve to exactly one source record"
    reactor_parents = list(g.objects(reactor_nodes[0], CORE.hasRecordedParent))
    assert len(reactor_parents) == 1
    reactor_assembly = reactor_parents[0]
    assert (reactor_assembly, EBOM.hasBOMItemId, Literal("ASM-REACTOR")) in g
    found = set()
    for assoc in rdf_associations:
        if (assoc, CORE.functionalAssociationTarget, reactor_assembly) not in g:
            continue
        source = next(g.objects(assoc, CORE.functionalAssociationSource))
        if ((source, EBOM.hasSourceDomain, Literal("DEXPI")) in g and
            (source, EBOM.hasSourceGroup, Literal("InstrumentationFunctions")) in g):
            found.update(str(x) for x in g.objects(source, EBOM.hasEngineeringLocalId))
    expected = {"FI_106", "LI_101", "PI_101", "TI_101", "TI_104"}
    assert found == expected, f"Q1-B mismatch: {found ^ expected}"
    # Independent traversal: each assembly has same number of functional links as source.
    counts = Counter(r["FunctionalAssemblyReference"] for r in source_associations)
    for assembly_id, count in counts.items():
        targets = list(g.subjects(EBOM.hasBOMItemId, Literal(assembly_id)))
        assert len(targets) == 1
        actual = sum((a, CORE.functionalAssociationTarget, targets[0]) in g for a in rdf_associations)
        assert actual == count, f"Functional count mismatch for {assembly_id}"
    return {
        "assemblies": len(assemblies),
        "bom_items": len(items),
        "parent_references": len(parent_refs),
        "functional_associations": len(rdf_associations),
        "reactor_instrumentation": sorted(found),
        "functional_associations_by_assembly": dict(sorted(counts.items())),
        "triple_count": len(g),
        "status": "PASS",
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ttl", type=Path, default=ROOT / "semantic/derived/tep_ebom_v2.ttl")
    p.add_argument("--input", type=Path, default=ROOT / "semantic/instances/tep/tep_engineering_bom_instance.json")
    p.add_argument("--shacl", action="store_true", help="Also run pyshacl against V2 constraints")
    args = p.parse_args()
    g = Graph().parse(args.ttl, format="turtle")
    doc = json.loads(args.input.read_text(encoding="utf-8"))
    result = validate(g, doc)
    if args.shacl:
        try:
            from pyshacl import validate as shacl_validate
        except ImportError as e:
            raise SystemExit("Install optional dependency: python -m pip install pyshacl") from e
        conforms, _, report = shacl_validate(
            g, shacl_graph=str(ROOT / "semantic/ontology/ebom_v2_shapes.ttl"),
            inference="none", abort_on_first=False)
        if not conforms:
            raise AssertionError("SHACL validation failed:\n" + str(report))
        result["shacl"] = "PASS"
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
