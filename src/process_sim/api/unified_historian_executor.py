"""Read-only TimescaleDB observations and exact signal-key row joining.

Consumes one already-validated SemanticQuery. No separate NL interpreter.
GraphDB must supply a SHACL-grounded operational signal projection; this
module never guesses signal bindings from asset names or LocalIDs.
"""
from uuid import UUID
import math

from process_sim.api.unified_semantic_ir import SemanticQuery


def _historian_plan(plan):
    if not isinstance(plan, SemanticQuery) or not plan.validated:
        raise ValueError("Validated semantic query required")
    if "timescaledb" not in plan.sources:
        raise ValueError("Semantic query has no historian source")
    if plan.aggregation is not None or plan.group_by or plan.where is not None or plan.order_by:
        raise ValueError("Historian aggregation, filters and ordering are not implemented")
    return str(UUID(str(plan.run_id)))


def retrieve_unified_samples(plan, dsn, signals, *, connection_factory=None, max_signals=100,
                             max_rows=10000):
    """Fetch bounded, run-scoped observations for explicitly resolved signal IDs.

    Returns rows with signal_id, simulationTimeHours, value, observedAt.
    The SQL and identifiers are static; user values are always parameters.
    """
    run_id = _historian_plan(plan)
    if not isinstance(signals, (list, tuple)) or not signals or len(signals) > max_signals:
        raise ValueError("Expected bounded nonempty resolved signal list")
    if any(not isinstance(s, str) or not s.strip() for s in signals):
        raise ValueError("Invalid signal identifier")
    signals = tuple(dict.fromkeys(signals))
    if type(max_rows) is not int or not 1 <= max_rows <= 100000:
        raise ValueError("Invalid historian row limit")
    if connection_factory is None:
        import psycopg
        connection_factory = psycopg.connect
    clauses = ["run_id = %s::uuid", "signal_id = ANY(%s)"]
    params = [run_id, list(signals)]
    if plan.start_seconds is not None:
        clauses.append("simulation_time_hours >= %s")
        params.append(plan.start_seconds / 3600.0)
    if plan.end_seconds is not None:
        clauses.append("simulation_time_hours <= %s")
        params.append(plan.end_seconds / 3600.0)
    sql = ("SELECT signal_id, simulation_time_hours, value, observed_at "
           "FROM public.signal_samples WHERE " + " AND ".join(clauses) +
           " ORDER BY signal_id, simulation_time_hours, observed_at, value LIMIT %s")
    params.append(max_rows + 1)
    with connection_factory(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                fetched = cur.fetchall()
    if len(fetched) > max_rows:
        raise ValueError("Historian row limit exceeded; narrow the query")
    rows = []
    for signal, hours, value, observed_at in fetched:
        if signal not in signals or not all(math.isfinite(float(v)) for v in (hours, value)):
            raise ValueError("Unexpected or non-finite historian observation")
        rows.append({"signal_id": signal, "simulationTimeHours": float(hours),
                     "value": float(value), "observedAt": observed_at.isoformat()})
    return rows


def join_graph_observations(graph_rows, observations, *, signal_field, max_rows=10000):
    """Inner join on exact operational signal ID; preserve graph row identity."""
    if not isinstance(signal_field, str) or not signal_field:
        raise ValueError("Explicit GraphDB signal field required")
    if not isinstance(graph_rows, list) or not isinstance(observations, list):
        raise ValueError("Expected graph and historian rows")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("Invalid join limit")
    indexed = {}
    for row in observations:
        if not isinstance(row, dict) or not isinstance(row.get("signal_id"), str):
            raise ValueError("Invalid observation row")
        indexed.setdefault(row["signal_id"], []).append(row)
    joined = []
    for graph in graph_rows:
        if not isinstance(graph, dict) or not isinstance(graph.get(signal_field), str):
            raise ValueError("GraphDB row lacks explicit operational signal")
        for observation in indexed.get(graph[signal_field], []):
            joined.append({"engineering": dict(graph), "observation": dict(observation)})
            if len(joined) > max_rows:
                raise ValueError("Cross-source join row limit exceeded")
    return joined


def execute_unified_historian(plan, dsn, *, graph_rows, signal_field,
                              connection_factory=None):
    """Execute historian-only or mixed using explicit live GraphDB signal rows.

    The caller must obtain graph_rows from a SHACL-grounded GraphDB query;
    this function never manufactures an engineering-to-signal mapping.
    """
    _historian_plan(plan)
    if not isinstance(graph_rows, list) or not graph_rows:
        raise ValueError("Live GraphDB signal resolution required")
    signals = []
    for row in graph_rows:
        if not isinstance(row, dict) or not isinstance(row.get(signal_field), str):
            raise ValueError("GraphDB signal projection missing")
        signals.append(row[signal_field])
    observations = retrieve_unified_samples(
        plan, dsn, signals, connection_factory=connection_factory)
    joined = join_graph_observations(graph_rows, observations, signal_field=signal_field)
    return {"rows": joined, "count": len(joined),
            "join_type": "exact_operational_signal_inner_join",
            "timeBasis": "simulation_time",
            "physicalSensorBinding": "NOT_VERIFIED",
            "sharedRunProvenance": "NOT_VERIFIED"}
