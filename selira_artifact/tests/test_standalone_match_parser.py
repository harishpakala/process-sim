import pytest

from selira.language.ast.contracts import MatchRule, UniqueRule
from selira.language.parser.contracts import parse_contract, CompilationError


def specification(rule):
    return ('Specification Test { Ref SubmodelTemplate sources = "aQ=="; '
            'Contract SC_02 { forall source in sources { ' + rule + ' } } }')


def test_standalone_match():
    rule = parse_contract(specification(
        "matches(source.LocalId, source.AssetIdentifier);")).contracts[0].rule
    assert rule == MatchRule("source", "sources", "source", "LocalId",
                             "source", "AssetIdentifier")


def test_unique_rule_preserved():
    rule = parse_contract(specification(
        "existsExactlyOne target in sources where matches(source.AssetIdentifier, target.AssetIdentifier);")).contracts[0].rule
    assert isinstance(rule, UniqueRule)


def test_standalone_match_rejects_unbound_variable():
    with pytest.raises(CompilationError):
        parse_contract(specification("matches(source.LocalId, other.AssetIdentifier);"))
