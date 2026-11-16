"""CLI orchestration tests with a single injected Qwen interpretation."""
import pytest
from process_sim.api.unified_cli import run_unified_cli

URI = "https://example.org/dexpi/hasSignalName"
RUN = "00000000-0000-0000-0000-000000000001"


class Schema:
    concepts = [{"kind": "shape", "domain": "DEXPI", "uri": "shape:instrument"}]
    by_uri = {}

    def shacl_paths(self, root, max_depth=5, domain=None):
        return [[{"property": URI, "evidence_ids": ["shacl:path"]}]]


def model(question, catalog, context, *, historian=False):
    return dict(
        projections=[{"name": "signalName", "source": "graphdb", "path_id": 0,
                      "alias": "instrument"}] +
                    ([{"name": "samples", "source": "timescaledb", "path_id": None}]
                     if historian else []),
        joins=[], where=None, group_by=[], aggregation=None, order_by=[],
        limit=None, sources=["graphdb", "timescaledb"] if historian else ["graphdb"],
        run_id=context.get("run_id"), start_seconds=context.get("start_seconds"),
        end_seconds=context.get("end_seconds"),
    )


def test_engineering_cli_calls_interpreter_once():
    calls = []
    def interpret(q, catalog, ctx):
        calls.append(q)
        return model(q, catalog, ctx)
    report = run_unified_cli(
        "Show engineering signal names", schema=Schema(), interpret=interpret,
        environ={"GRAPHDB_SPARQL_ENDPOINT": "http://unused"},
        graph_executor=lambda endpoint, sparql: [{"signalName": "S1"}])
    assert calls == ["Show engineering signal names"]
    assert report["answer"]["rows"] == [{"signalName": "S1"}]
    assert report["executed"] is True


def test_mixed_cli_joins_live_graph_rows_to_timescale_samples():
    from datetime import datetime, timezone
    class FakeConnection:
        def __init__(self):
            self.statements = []
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def transaction(self):
            return self
        def execute(self, statement):
            self.statements.append(statement)
        def cursor(self):
            return self
        def fetchall(self):
            return [("S1", 1.5, 3.2, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    conn = FakeConnection()
    connect = lambda dsn: conn
    report = run_unified_cli(
        "Show engineering signal observations", schema=Schema(),
        context={"run_id": RUN},
        interpret=lambda q, c, x: model(q, c, x, historian=True),
        environ={"GRAPHDB_SPARQL_ENDPOINT": "http://unused",
                 "TEP_TIMESCALE_DSN": "unused"},
        graph_executor=lambda endpoint, sparql: [{"signalName": "S1"}],
        connection_factory=connect, signal_field="signalName")
    assert report["answer"]["count"] == 1
    assert report["answer"]["rows"][0]["engineering"]["signalName"] == "S1"
    assert conn.statements == ["SET TRANSACTION READ ONLY"]


def test_mixed_cli_requires_explicit_signal_field():
    with pytest.raises(ValueError, match="signal projection"):
        run_unified_cli(
            "Show engineering signal observations", schema=Schema(),
            context={"run_id": RUN},
            interpret=lambda q, c, x: model(q, c, x, historian=True),
            dry_run=True)


def test_dry_run_never_calls_database():
    report = run_unified_cli(
        "Show engineering signal names", schema=Schema(),
        interpret=lambda q, c, x: model(q, c, x), dry_run=True)
    assert report["executed"] is False
    assert "SELECT DISTINCT" in report["sparql"]
