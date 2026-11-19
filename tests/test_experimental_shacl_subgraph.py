"""Regression tests for the experimental DEXPI subgraph extractor."""
from pathlib import Path

from process_sim.dtwise.experimental_shacl_subgraph import load_index, extract_question

INDEX = Path(__file__).resolve().parents[1] / "semantic" / "ontology2" / "dtwise" / "dtwise-schema-index.json"


def _index():
    # Resolve from repository root without depending on current working directory.
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "semantic/ontology2/dtwise/dtwise-schema-index.json"
        if candidate.exists():
            return load_index(candidate)
    raise FileNotFoundError("DEXPI schema index fixture not found")


def test_instrumentation_property_without_root():
    result = extract_question(_index(), "Show MeasuredVariable from InstrumentationFunction")
    assert any(n["name"] == "InstrumentationFunction" for n in result["nodes"])
    assert any(p["predicate"].endswith("/hasMeasuredVariable") for p in result["properties"])
    assert not result["edges"]


def test_actuating_property_without_root():
    result = extract_question(_index(), "Show ActuatedVariable from ActuatingFunction")
    assert any(n["name"] == "ActuatingFunction" for n in result["nodes"])
    assert any(p["predicate"].endswith("/hasActuatedVariable") for p in result["properties"])


def test_independent_functions_remain_disconnected():
    result = extract_question(
        _index(),
        "Show MeasuredVariable of InstrumentationFunction and ActuatedVariable of ActuatingFunction",
    )
    assert len(result["nodes"]) == 2
    assert result["edges"] == []
    assert {p["predicate"].rsplit("/", 1)[-1] for p in result["properties"]} == {
        "hasMeasuredVariable", "hasActuatedVariable"
    }


def test_root_to_instrumentation_evidence():
    index = _index()
    root = next(uri for uri, c in index.shapes.items() if "DEXPI" in c.get("labels", []))
    instrument = next(uri for uri, c in index.shapes.items() if "InstrumentationFunction" in c.get("labels", []))
    result = index.extract([root, instrument], connect=True)
    assert any(e["predicate"].endswith("/hasInstrumentationFunction") for e in result["edges"])
    assert all(e["evidence"] for e in result["edges"])


def _domain_index(domain):
    return load_index(INDEX, domain=domain)


def _assert_nested_path(domain, question, node_names, predicates, property_name):
    result = extract_question(_domain_index(domain), question, connect=True)
    assert {n["name"] for n in result["nodes"]} == set(node_names)
    assert {e["predicate"].rsplit("/", 1)[-1] for e in result["edges"]} == set(predicates)
    assert len(result["properties"]) == 1
    assert result["properties"][0]["name"] == property_name
    assert result["unresolved_connections"] == []
    assert all(edge["evidence"] for edge in result["edges"])


def test_opcua_nested_signal_mapping():
    _assert_nested_path(
        "opcuaconnectivity",
        "Show OPCUANodeId of SignalMapping in TEP_OPCUAConnectivity",
        {"TEP_OPCUAConnectivity", "SignalMapping"},
        {"hasSignalMapping"},
        "OPCUANodeId",
    )


def test_assetinventory_nested_asset():
    _assert_nested_path(
        "assetinventory",
        "Show EquipmentTag of Asset in AssetInventory",
        {"AssetInventory", "Asset"},
        {"hasAsset"},
        "EquipmentTag",
    )


def test_ecad_device_endpoint_not_symbol_or_plc():
    result = extract_question(
        _domain_index("ecad"),
        "Show Address of EndPoint belonging to Device in ECAD",
        connect=True,
    )
    assert {n["name"] for n in result["nodes"]} == {"ECAD", "Device", "EndPoint"}
    assert len(result["nodes"]) == 3
    assert len(result["edges"]) == 2
    assert len(result["properties"]) == 1
    assert result["properties"][0]["name"] == "Address"
    assert result["unresolved_connections"] == []
    assert "ambiguous_paths" not in result
    assert all(e["evidence"] for e in result["edges"])


def test_ecad_leaf_only_address_preserves_four_alternatives():
    """An underspecified leaf must not silently choose Device/Symbol or PLC."""
    result = extract_question(
        _domain_index("ecad"), "Show Address in ECAD", connect=True
    )
    assert len(result["nodes"]) == 7
    assert len(result["edges"]) == 6
    assert len(result["properties"]) == 4
    assert len(result["ambiguous_paths"]) == 4
    assert len({p["target"] for p in result["ambiguous_paths"]}) == 4
    assert result["unresolved_connections"] == []
    assert all(edge["evidence"] for edge in result["edges"])
    assert all(prop["evidence"] for prop in result["properties"])


def test_dexpi_independent_branches_with_explicit_root_remain_disconnected():
    """A shared domain name alone is not an instruction to join siblings."""
    result = extract_question(
        _domain_index("dexpi"),
        "In DEXPI show MeasuredVariable of InstrumentationFunction "
        "and ActuatedVariable of ActuatingFunction",
        connect=False,
    )
    assert {p["name"] for p in result["properties"]} == {
        "MeasuredVariable", "ActuatedVariable"
    }
    assert result["edges"] == []
    assert result["unresolved_connections"] == []



def test_ecad_cross_branch_address_candidates_remain_disconnected():
    """Mentioning both branches does not imply a join when connect=False."""
    result = extract_question(
        _domain_index("ecad"),
        "Show Address of EndPoint in Device and Symbol in ECAD",
        connect=False,
    )
    assert result["edges"] == []
    assert len(result["properties"]) == 4
    assert len({p["owner"] for p in result["properties"]}) == 4
    assert result["unresolved_connections"] == []
