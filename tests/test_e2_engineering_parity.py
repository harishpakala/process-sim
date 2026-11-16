"""Offline tests for E2 comparison, including fail-closed mismatch cases."""
from process_sim.api.e2_engineering_parity import compare_engineering_question

URI = "https://example.org/dexpi/hasAssetIdentifier"


def old(values):
    return {"mode": "frozen_dtwise_graphdb", "executed": True,
            "sparql": "SELECT ?value WHERE { ?s ?p ?value }",
            "answer": {"intent": "list", "property": URI,
                       "values": [{"entity": "e", "value": v} for v in values],
                       "count": len(values), "truncated_possible": False}}


def new(values, *, property_uri=URI):
    return {"executed": True,
            "sparql": "SELECT DISTINCT ?AssetIdentifier WHERE { ?s ?p ?o }",
            "plan": {"sources": ["graphdb"], "projections": [{
                "name": "AssetIdentifier",
                "path": {"predicates": ["https://example.org/dexpi/hasInstrumentationFunction",
                                         property_uri]}}]},
            "graph": {"rows": [{"AssetIdentifier": v} for v in values],
                      "count": len(values), "truncated_possible": False}}


def compare(legacy, unified):
    return compare_engineering_question(
        "Show DEXPI instrumentation AssetIdentifier",
        field="AssetIdentifier", property_uri=URI,
        legacy_runner=lambda q: legacy,
        unified_runner=lambda q, schema: unified,
        schema=object())


def test_e2_identical_value_sets_match_independent_of_row_order():
    report = compare(old(["A", "B"]), new(["B", "A"]))
    assert report["status"] == "MATCH"
    assert report["only_legacy"] == report["only_unified"] == []


def test_e2_missing_value_reports_mismatch_not_success():
    report = compare(old(["A", "B"]), new(["A"]))
    assert report["status"] == "MISMATCH"
    assert report["only_legacy"] == ["B"]


def test_e2_wrong_unified_shacl_property_is_inconclusive():
    report = compare(old(["A"]), new(["A"], property_uri=URI + "Wrong"))
    assert report["status"] == "INCONCLUSIVE"
    assert "wrong terminal SHACL predicate" in report["unified"]["error"]


def test_e2_legacy_aggregate_cannot_be_misreported_as_parity():
    legacy = old(["A"])
    legacy["answer"]["intent"] = "count"
    report = compare(legacy, new(["A"]))
    assert report["status"] == "INCONCLUSIVE"


def test_e2_truncated_results_cannot_be_misreported_as_parity():
    legacy = old(["A"])
    legacy["answer"]["truncated_possible"] = True
    assert compare(legacy, new(["A"]))["status"] == "INCONCLUSIVE"
    unified = new(["A"])
    unified["graph"]["truncated_possible"] = True
    assert compare(old(["A"]), unified)["status"] == "INCONCLUSIVE"


def test_e2_legacy_error_is_inconclusive():
    def fail(question):
        raise RuntimeError("legacy planner unsupported")
    report = compare_engineering_question(
        "Show DEXPI instrumentation AssetIdentifier",
        field="AssetIdentifier", property_uri=URI,
        legacy_runner=fail,
        unified_runner=lambda q, schema: new(["A"]), schema=object())
    assert report["status"] == "INCONCLUSIVE"
    assert "legacy planner unsupported" in report["legacy"]["error"]
