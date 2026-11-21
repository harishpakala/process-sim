"""Offline tests for read-only SPARQL endpoint execution."""
import json
from io import BytesIO
from unittest.mock import patch

import pytest

from benchmarks.shacl_phase1.execute_single_domain_sparql import (
    execute_query, execute_results,
)


class Response(BytesIO):
    pass


def test_select_with_results():
    payload = {"head": {"vars": ["s"]},
               "results": {"bindings": [{"s": {"type": "uri", "value": "urn:a"}}]}}
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen",
               return_value=Response(json.dumps(payload).encode())) as mock:
        result = execute_query("http://localhost:7200/repositories/AAST",
                               "SELECT ?s WHERE { ?s ?p ?o }")
    assert result["status"] == "executed_with_results"
    assert result["row_count"] == 1
    assert mock.call_args.args[0].get_method() == "POST"


def test_zero_rows_is_success():
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen",
               return_value=Response(b'{"results":{"bindings":[]}}')):
        result = execute_query("http://localhost:7200/repositories/AAST",
                               "SELECT ?s WHERE { ?s ?p ?o }")
    assert result["status"] == "executed_zero_rows"
    assert result["row_count"] == 0


def test_rejects_non_select_without_network():
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen") as mock:
        result = execute_query("http://localhost:7200/repositories/AAST",
                               "DELETE WHERE { ?s ?p ?o }")
    assert result["status"] == "unsupported_query"
    mock.assert_not_called()


def test_failed_request_is_reported():
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen",
               side_effect=OSError("offline")):
        result = execute_query("http://localhost:7200/repositories/AAST",
                               "SELECT * WHERE { ?s ?p ?o }")
    assert result["status"] == "execution_failed"


def test_batch_preserves_uncompiled():
    result = execute_results([{"id": "A", "status": "compilation_failed",
                               "error": "bad"}], "http://localhost:7200")
    assert result[0]["status"] == "not_compiled"
    assert result[0]["semantic_status"] == "not_checked"


def test_batch_rejects_duplicates():
    with pytest.raises(ValueError, match="Duplicate"):
        execute_results([{"id": "A"}, {"id": "A"}], "http://localhost:7200")
