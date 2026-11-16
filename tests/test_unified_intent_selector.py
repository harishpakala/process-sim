"""Offline checks for the common SHACL-catalog intent selector."""
from unittest.mock import patch

import pytest

from process_sim.api.unified_intent_selector import select_semantic_intent

CATALOG = [{"domain": "DEXPI", "entity": "InstrumentationFunction"}]


@pytest.mark.parametrize("intent", ["graph_query", "observations", "mixed"])
def test_both_domains_share_one_selection_interface(intent):
    with patch("process_sim.api.unified_intent_selector._schema_catalog", return_value=CATALOG):
        observed = []
        def interpret(question, catalog):
            observed.append(catalog)
            return {"intent": intent}
        assert select_semantic_intent("Describe DEXPI FI_101", object(), interpret=interpret) == intent
        assert observed == [CATALOG]


@pytest.mark.parametrize("response", [
    {"intent": "sql"}, {"intent": "graph_query", "sql": "DROP TABLE x"},
    {"intent": "unsupported"}, None,
])
def test_invalid_or_unsupported_model_response_fails_closed(response):
    with patch("process_sim.api.unified_intent_selector._schema_catalog", return_value=CATALOG):
        with pytest.raises(ValueError):
            select_semantic_intent("Describe DEXPI FI_101", object(),
                                   interpret=lambda q, c: response)


def test_empty_shacl_catalog_fails_before_model():
    with patch("process_sim.api.unified_intent_selector._schema_catalog", return_value=[]):
        with pytest.raises(ValueError, match="SHACL"):
            select_semantic_intent("Describe DEXPI FI_101", object(),
                                   interpret=lambda q, c: {"intent": "graph_query"})
