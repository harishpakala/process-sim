"""Actual EngineeringBOM SHACL topology regression tests.

These tests use the checked-in schema index, not a fabricated BOM hierarchy.
"""
from pathlib import Path

from process_sim.dtwise.experimental_shacl_subgraph import load_index


INDEX = (Path(__file__).resolve().parents[1] / "semantic" / "ontology2"
         / "dtwise" / "dtwise-schema-index.json")


def _engineeringbom():
    return load_index(INDEX, domain="engineeringbom")


def _labels(index):
    return {uri: next(iter(shape["labels"])) for uri, shape in index.shapes.items()}


def test_engineeringbom_root_has_four_verified_record_branches():
    index = _engineeringbom()
    names = _labels(index)
    edges = {(names[e["from"]], names[e["to"]], e["predicate"].rsplit("/", 1)[-1])
             for e in index.edges}
    assert edges == {
        ("TEP_EngineeringBOM_V2_Template", "AssemblyRecord", "hasAssemblyRecord"),
        ("TEP_EngineeringBOM_V2_Template", "BOMItemRecord", "hasBOMItemRecord"),
        ("TEP_EngineeringBOM_V2_Template", "FunctionalAssociation", "hasFunctionalAssociation"),
        ("TEP_EngineeringBOM_V2_Template", "ParentLink", "hasParentLink"),
    }


def test_engineeringbom_no_recursive_assembly_edge_in_current_index():
    index = _engineeringbom()
    names = _labels(index)
    assert not any(names[e["from"]] != "TEP_EngineeringBOM_V2_Template"
                   for e in index.edges)
    assert not any(e["from"] == e["to"] for e in index.edges)


def test_engineeringbom_bom_item_property_has_valid_root_path():
    index = _engineeringbom()
    names = _labels(index)
    root = next(uri for uri, label in names.items()
                if label == "TEP_EngineeringBOM_V2_Template")
    bom = next(uri for uri, label in names.items()
               if label == "BOMItemRecord")
    edge = next(e for e in index.edges if e["from"] == root and e["to"] == bom)
    props = index.properties[bom]
    prop = next(p for p in props if p["name"] == "EngineeringLocalId")
    assert edge["predicate"] == "https://example.org/engineeringbom/hasBOMItemRecord"
    assert prop["predicate"] == "https://example.org/engineeringbom/hasEngineeringLocalId"
    assert prop["owner"] == bom
