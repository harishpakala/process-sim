"""Independent SQL comparison for the TEP NEXUS live virtual graph.

The expected historian rows are queried through a separate SQL statement,
not through retrieve_observations, the function registry, or pipeline validators.
The function-to-signal expected mappings are a fixed, independently reviewed
fixture, not discovered from the live function registry.
"""
import argparse
import json
import os
from datetime import timezone
from pathlib import Path
from uuid import UUID

import psycopg
from tep_nexus_live_virtual_graph import execute

# Explicit, independently reviewable expected mappings for the four paper instruments.
EXPECTED_SIGNALS = {"PI_101": "XMEAS7", "FI_106": "XMEAS6",
                    "TI_101": "XMEAS9", "LI_101": "XMEAS8"}


def canonical_stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def sql_oracle(dsn, run_id, signal, start_seconds, end_seconds, limit):
    # Separate query design: select full matching set in a CTE, number ordered
    # rows, then retrieve up to limit; count all matching rows independently.
    sql = """
    WITH matching AS (
      SELECT simulation_time_hours, value, observed_at
      FROM public.signal_samples
      WHERE run_id = %(run)s::uuid AND signal_id = %(signal)s
        AND simulation_time_hours * 3600.0 >= %(start)s
        AND simulation_time_hours * 3600.0 <= %(end)s
    ), numbered AS (
      SELECT simulation_time_hours, value, observed_at,
             row_number() OVER (
               ORDER BY simulation_time_hours ASC, observed_at ASC, value ASC
             ) AS ordinal
      FROM matching
    )
    SELECT simulation_time_hours, value, observed_at
    FROM numbered WHERE ordinal <= %(limit)s ORDER BY ordinal
    """
    count_sql = """
    SELECT count(*) FROM public.signal_samples
    WHERE run_id = %(run)s::uuid AND signal_id = %(signal)s
      AND simulation_time_hours * 3600.0 >= %(start)s
      AND simulation_time_hours * 3600.0 <= %(end)s
    """
    params = {"run": str(UUID(run_id)), "signal": signal, "start": start_seconds,
              "end": end_seconds, "limit": limit}
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                count = cur.fetchone()[0]
                cur.execute(sql, params)
                rows = cur.fetchall()
    return [(float(h), float(v), canonical_stamp(t)) for h, v, t in rows], count > limit, count


def graph_rows(graph):
    return [(float(n["simulationTimeHours"]), float(n["value"]),
             canonical_stamp(__import__("datetime").datetime.fromisoformat(n["observedAt"])))
            for n in graph["nodes"] if n["type"] == "VirtualObservation"]


def run_case(dsn, graphdb_url, run_id, function, start, end, limit, mapping_discovery, temporal_coverage):
    expected_signal = EXPECTED_SIGNALS[function]
    graph = execute({"engineering_function": function, "run_id": run_id,
                     "start_simulation_seconds": start, "end_simulation_seconds": end,
                     "limit": limit}, dsn=dsn, graphdb_url=graphdb_url,
                    mapping_discovery=mapping_discovery, temporal_coverage=temporal_coverage)
    signal_nodes = [n["signalId"] for n in graph["nodes"] if n["type"] == "OperationalSignal"]
    actual = graph_rows(graph)
    expected, expected_truncated, full_count = sql_oracle(
        dsn, run_id, expected_signal, start, end, limit)
    checks = {
        "signal_matches_independent_fixture": signal_nodes == [expected_signal],
        "ordered_rows_exact": actual == expected,
        "count_matches": graph["result"]["observationCount"] == len(expected),
        "truncation_matches": graph["result"]["truncated"] == expected_truncated,
        "run_matches": graph["request"]["run_id"] == str(UUID(run_id)),
    }
    mismatch = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), None)
    return {"function": function, "signal": expected_signal, "windowSeconds": [start, end],
            "limit": limit, "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "live_count": len(actual), "oracle_full_count": full_count,
            "oracle_truncated": expected_truncated, "first_mismatch_index": mismatch,
            "live_row_count": len(actual), "oracle_row_count": len(expected)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--window", type=float, nargs=2, action="append", required=True)
    p.add_argument("--function", action="append", choices=sorted(EXPECTED_SIGNALS))
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", default="reports/tep_nexus_independent_sql_oracle.json")
    a = p.parse_args()
    if a.limit < 1 or a.limit > 5000 or any(s < 0 or e < s for s, e in a.window):
        p.error("Invalid limit or window")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is required")
    cases = []
    for function in (a.function or list(EXPECTED_SIGNALS)):
        for start, end in a.window:
            try:
                cases.append(run_case(dsn, a.graphdb_url, a.run_id, function, start,
                                      end, a.limit, a.mapping_discovery, a.temporal_coverage))
            except Exception as exc:
                cases.append({"function": function, "windowSeconds": [start, end],
                              "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    report = {"scope": "independent_sql_observation_comparison_four_fixed_mapping_fixtures",
              "oracle": "separate read-only TimescaleDB SQL, same source table",
              "limitations": [
                  "Independent of live retrieval SQL implementation and function registry for expected values, but shares the same underlying TimescaleDB historian.",
                  "Four expected engineering-to-signal mappings are fixed fixtures requiring external review.",
                  "Not independent physical installation, provenance, or fault-activation verification.",
                  "Live and oracle queries execute separately; use an immutable simulation run or snapshot to prevent concurrent-write differences."
              ],
              "cases": cases, "summary": {"total": len(cases),
                  "passed": sum(c["status"] == "PASS" for c in cases),
                  "failed": sum(c["status"] != "PASS" for c in cases)}}
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **report["summary"]}, indent=2))
    raise SystemExit(0 if report["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
