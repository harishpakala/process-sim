"""Offline acceptance checks for the narrow live mixed-query script."""
import pytest
from scripts.unified_mixed_live_experimental import parse_question, engineering_details

QUESTION = ("Show the engineering details of DEXPI InstrumentationFunction FI_101 "
            "and its recorded measurements between simulation seconds 100 and 300 "
            "for run 077a3c31-44f4-4f3a-b06d-ad52b148fe10.")


def test_parse_exact_supported_question():
    assert parse_question(QUESTION) == (
        "FI_101", "077a3c31-44f4-4f3a-b06d-ad52b148fe10", 100.0, 300.0)


def test_reject_unsupported_or_ambiguous_question():
    with pytest.raises(ValueError, match="supported"):
        parse_question(QUESTION + " Also show ECAD components.")


def test_details_use_whitelisted_predicates_and_resolved_entity():
    evidence = {"properties": [
        {"property": "https://example.org/dexpi/hasLocalId"},
        {"property": "https://example.org/dexpi/hasAssetIdentifier"}]}
    queries = []
    def executor(endpoint, query):
        queries.append(query)
        return [{"predicate": "https://example.org/dexpi/hasLocalId",
                 "value": "FI_101"}]
    result = engineering_details("http://example.invalid/sparql",
                                 "https://example.org/entity/FI101", evidence,
                                 executor=executor)
    assert result["property_count"] == 1
    assert queries[0].startswith("SELECT ")
    assert "<https://example.org/entity/FI101>" in queries[0]
    assert "VALUES ?predicate" in queries[0]


def test_details_reject_unapproved_property():
    with pytest.raises(ValueError, match="Unexpected"):
        engineering_details("http://example.invalid/sparql",
                            "https://example.org/entity/FI101",
                            {"properties": [{"property": "https://example.org/dexpi/hasLocalId"}]},
                            executor=lambda *_: [{"predicate": "https://example.org/other",
                                                  "value": "x"}])
