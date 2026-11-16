"""Offline TimescaleDB and cross-source join tests."""
from datetime import datetime, timezone

import pytest

from process_sim.api.unified_semantic_ir import Projection, SemanticQuery
from process_sim.api.unified_historian_executor import (
    execute_unified_historian, join_graph_observations, retrieve_unified_samples,
)

RUN = "00000000-0000-0000-0000-000000000001"


class Schema:
    def shacl_paths(self, *args, **kwargs):
        return []


def plan(**kwargs):
    values = dict(
        question="Show observations for selected engineering signal",
        projections=(Projection("observations", source="timescaledb"),),
        sources=("timescaledb",), run_id=RUN, start_seconds=3600,
        end_seconds=7200,
    )
    values.update(kwargs)
    return SemanticQuery(**values).validate(Schema())


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.cur = Cursor(rows)
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
        return self.cur


def factory(rows):
    connection = Connection(rows)
    return connection, lambda dsn: connection


def test_parameterized_read_only_retrieval():
    conn, connect = factory([("S1", 1.5, 3.2, datetime(2026, 1, 1, tzinfo=timezone.utc))])
    rows = retrieve_unified_samples(plan(), "unused", ["S1"], connection_factory=connect)
    assert rows[0]["signal_id"] == "S1"
    assert conn.statements == ["SET TRANSACTION READ ONLY"]
    assert "signal_id = ANY(%s)" in conn.cur.sql
    assert conn.cur.params[:4] == [RUN, ["S1"], 1.0, 2.0]


def test_exact_row_join_excludes_unmatched_signals():
    rows = join_graph_observations(
        [{"asset": "A", "signal": "S1"}, {"asset": "B", "signal": "S2"}],
        [{"signal_id": "S1", "value": 42}], signal_field="signal")
    assert len(rows) == 1
    assert rows[0]["engineering"]["asset"] == "A"
    assert rows[0]["observation"]["value"] == 42


def test_mixed_execution_preserves_graph_identity():
    conn, connect = factory([("S1", 1.5, 3.2, datetime(2026, 1, 1, tzinfo=timezone.utc))])
    result = execute_unified_historian(
        plan(), "unused", graph_rows=[{"asset": "A", "signal": "S1"}],
        signal_field="signal", connection_factory=connect)
    assert result["join_type"] == "exact_operational_signal_inner_join"
    assert result["rows"][0]["engineering"]["asset"] == "A"


def test_missing_signal_mapping_fails_closed():
    with pytest.raises(ValueError, match="signal projection"):
        execute_unified_historian(
            plan(), "unused", graph_rows=[{"asset": "A"}],
            signal_field="signal", connection_factory=lambda dsn: None)


def test_historian_aggregation_is_not_silently_ignored():
    with pytest.raises(ValueError, match="not implemented"):
        retrieve_unified_samples(plan(aggregation="avg"), "unused", ["S1"],
                                 connection_factory=lambda dsn: None)


def test_join_size_limit_rejected():
    with pytest.raises(ValueError, match="limit"):
        join_graph_observations(
            [{"signal": "S1"}], [{"signal_id": "S1"}, {"signal_id": "S1"}],
            signal_field="signal", max_rows=1)
