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
