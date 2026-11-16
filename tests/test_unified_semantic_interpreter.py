"""Offline tests for one model call and one shared SHACL-grounded query."""
from uuid import uuid4
import pytest

from process_sim.api.unified_semantic_interpreter import interpret_unified_semantics


class SchemaStub:
    concepts = [{"kind": "shape", "domain": "DEXPI", "uri": "shape:instrument"}]
    by_uri = {"dexpi:assetIdentifier": {"labels": ["AssetIdentifier"]}}

    def shacl_paths(self, root, max_depth=5, domain=None):
        if root == "shape:instrument" and domain == "DEXPI":
            return [[{"property": "dexpi:assetIdentifier",
                      "evidence_ids": ["edge:property", "edge:path"]}]]
        return []


QUESTION = "Show engineering identifiers and historian observations"


def response(**changes):
    result = dict(
        projections=[{"name": "assetIdentifier", "path_id": 0, "source": "graphdb"}],
        joins=[], where=None, group_by=[], aggregation=None, order_by=[],
        limit=None, sources=["graphdb"], run_id=None,
        start_seconds=None, end_seconds=None)
    result.update(changes)
    return result


def test_one_interpretation_for_engineering():
    calls = []
    def model(question, catalog, context):
        calls.append((question, catalog, context))
        return response()
    query = interpret_unified_semantics(QUESTION, SchemaStub(), interpret=model)
    assert len(calls) == 1
    assert query.validated
    assert query.projections[0].path.evidence_ids == ("edge:property", "edge:path")


def test_same_interpreter_accepts_historian_and_mixed():
    run_id = str(uuid4())
    for sources, projections in [
        (["timescaledb"], [{"name": "observations", "path_id": None,
                            "source": "timescaledb"}]),
        (["graphdb", "timescaledb"], [
            {"name": "assetIdentifier", "path_id": 0, "source": "graphdb"},
            {"name": "observations", "path_id": None, "source": "timescaledb"}]),
    ]:
        query = interpret_unified_semantics(
            QUESTION, SchemaStub(), context={"run_id": run_id},
            interpret=lambda q, c, x: response(sources=sources, projections=projections))
        assert query.validated
        assert query.run_id == run_id
        assert query.sources == tuple(sources)


def test_invented_path_id_fails_closed():
    with pytest.raises(ValueError, match="catalog path"):
        interpret_unified_semantics(QUESTION, SchemaStub(),
                                    interpret=lambda q, c, x: response(
                                        projections=[{"name": "invented", "path_id": 99,
                                                      "source": "graphdb"}]))


def test_unexpected_model_fields_rejected():
    with pytest.raises(ValueError, match="unexpected"):
        interpret_unified_semantics(QUESTION, SchemaStub(),
                                    interpret=lambda q, c, x: response(route="engineering"))


def test_selected_run_cannot_be_overridden():
    with pytest.raises(ValueError, match="contradicted"):
        interpret_unified_semantics(
            QUESTION, SchemaStub(), context={"run_id": str(uuid4())},
            interpret=lambda q, c, x: response(run_id=str(uuid4())))


def test_nested_boolean_logic_survives_interpretation():
    expression = {"operator": "and", "children": [
        {"field": "assetIdentifier", "operator": "exists", "value": None},
        {"operator": "not", "children": [
            {"field": "equipmentTag", "operator": "exists", "value": None}]}]}
    query = interpret_unified_semantics(
        QUESTION, SchemaStub(), interpret=lambda q, c, x: response(where=expression))
    assert query.where.operator == "and"
    assert query.where.children[1].operator == "not"
