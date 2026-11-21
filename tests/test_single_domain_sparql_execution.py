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


def test_named_graph_is_passed_as_sparql_protocol_parameter():
    from urllib.parse import parse_qs
    payload = b'{"results":{"bindings":[]}}'
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen",
               return_value=Response(payload)) as mock:
        result = execute_query("http://localhost:7200/repositories/AAST",
                               "SELECT * WHERE { ?s ?p ?o }",
                               default_graph_uri="http://example.org/ecad")
    parameters = parse_qs(mock.call_args.args[0].data.decode())
    assert parameters["default-graph-uri"] == ["http://example.org/ecad"]
    assert result["status"] == "executed_zero_rows"


def test_comparison_preserves_both_dataset_counts():
    def respond(request, timeout):
        from urllib.parse import parse_qs
        parameters = parse_qs(request.data.decode())
        count = 1 if "default-graph-uri" in parameters else 2
        return Response(json.dumps({"results": {"bindings": [{}] * count}}).encode())
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen",
               side_effect=respond):
        result = execute_results(
            [{"id": "SD01-P1", "domain": "ecad", "status": "compiled",
              "sparql": "SELECT ?s WHERE { ?s ?p ?o }"}],
            "http://localhost:7200/repositories/AAST",
            graph_mapping={"ecad": "http://example.org/ecad"}, compare=True)[0]
    assert result["row_count"] == 1
    assert result["repository_default_row_count"] == 2
    assert result["row_count_delta"] == -1


def test_missing_domain_graph_fails_closed():
    with patch("benchmarks.shacl_phase1.execute_single_domain_sparql.urlopen") as mock:
        result = execute_results(
            [{"id": "SD01-P1", "domain": "ecad", "status": "compiled",
              "sparql": "SELECT ?s WHERE { ?s ?p ?o }"}],
            "http://localhost:7200/repositories/AAST",
            graph_mapping={"dexpi": "http://example.org/dexpi"})[0]
    assert result["status"] == "graph_mapping_missing"
    mock.assert_not_called()
