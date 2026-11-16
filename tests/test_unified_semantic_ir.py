"""Unit tests for the new shared semantic IR; no live services required."""
from dataclasses import replace
from uuid import uuid4

import pytest

from process_sim.api.unified_semantic_ir import (
    BooleanExpression, GraphPath, Join, Predicate, Projection, SemanticQuery,
)


class SchemaStub:
    def shacl_paths(self, root, max_depth=4, domain=None):
        if root != "shape:instrument" or domain != "DEXPI":
            return []
        return [[{"property": "dexpi:assetIdentifier",
                  "evidence_ids": ["edge:property", "edge:path"]}]]


PATH = GraphPath("DEXPI", "shape:instrument", ("dexpi:assetIdentifier",))


def test_shacl_path_is_grounded_with_evidence():
    grounded = PATH.validate(SchemaStub())
    assert grounded.evidence_ids == ("edge:property", "edge:path")


def test_unsupported_path_fails_closed():
    with pytest.raises(ValueError, match="SHACL"):
        replace(PATH, predicates=("dexpi:invented",)).validate(SchemaStub())


def test_model_cannot_invent_evidence():
    with pytest.raises(ValueError, match="evidence"):
        replace(PATH, evidence_ids=("invented",)).validate(SchemaStub())


def test_boolean_tree_preserves_nested_logic():
    expression = BooleanExpression("and", (
        Predicate("assetIdentifier", "exists"),
        BooleanExpression("not", (Predicate("equipmentTag", "exists"),)),
    ))
    query = SemanticQuery("Which assets have IDs but no equipment tags?",
                          (Projection("assetIdentifier", PATH),), where=expression)
    grounded = query.validate(SchemaStub())
    assert grounded.validated
    assert grounded.where == expression
    assert grounded.projections[0].path.evidence_ids


def test_mixed_query_has_one_semantic_representation():
    query = SemanticQuery(
        "Show engineering identifiers and recorded observations for this run",
        (Projection("assetIdentifier", PATH),
         Projection("observations", source="timescaledb")),
        sources=("graphdb", "timescaledb"), run_id=str(uuid4()),
        start_seconds=100, end_seconds=300)
    assert query.validate(SchemaStub()).validated


def test_historian_without_run_rejected():
    query = SemanticQuery("Show recorded observations for this sensor",
                          (Projection("observations", source="timescaledb"),),
                          sources=("timescaledb",))
    with pytest.raises(ValueError, match="run UUID"):
        query.validate(SchemaStub())


def test_join_validates_both_paths():
    join = Join("a", "b", PATH, replace(PATH, predicates=("unknown",)))
    with pytest.raises(ValueError, match="SHACL"):
        join.validate(SchemaStub())


@pytest.mark.parametrize("operator,children", [
    ("not", (Predicate("x", "exists"), Predicate("y", "exists"))),
    ("and", (Predicate("x", "exists"),)),
])
def test_boolean_arity_rejected(operator, children):
    with pytest.raises(ValueError, match="arity"):
        BooleanExpression(operator, children)
