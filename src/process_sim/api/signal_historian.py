"""Read-only signal-first historian endpoints; no GraphDB dependency."""
from __future__ import annotations

import math
import os
from uuid import UUID

import psycopg


def _dsn(environ=None):
    dsn = (os.environ if environ is None else environ).get("TEP_TIMESCALE_DSN")
    if not dsn:
        raise RuntimeError("Configure TEP_TIMESCALE_DSN")
    return dsn


MEASUREMENT_TYPES = ("Temperature", "Pressure", "Level", "Energy", "Unclassified")


def discover_measurement_types(*, environ=None, connection_factory=psycopg.connect):
    """Available classifications from signal metadata, including the unknown bucket."""
    with connection_factory(_dsn(environ)) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute("""SELECT measurement_type, COUNT(*) FROM public.signal_metadata
                    GROUP BY measurement_type ORDER BY measurement_type""")
                counts = dict(cur.fetchall())
    return {"measurement_types": [{"name": name, "signal_count": counts.get(name, 0)}
                                  for name in MEASUREMENT_TYPES],
            "source": "TimescaleDB public.signal_metadata"}


def discover_signals(run_id, *, measurement_type=None, environ=None, connection_factory=psycopg.connect):
    run = str(UUID(str(run_id)))
    if measurement_type is not None and measurement_type not in MEASUREMENT_TYPES:
        raise ValueError("Unsupported measurement_type")
    with connection_factory(_dsn(environ)) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute("""SELECT s.signal_id, COUNT(*),
                           COALESCE(m.measurement_type, 'Unclassified'), m.unit,
                           COALESCE(m.classification_source, 'unclassified'),
                           COALESCE(m.verification_status, 'NOT_VERIFIED')
                    FROM public.signal_samples s
                    LEFT JOIN public.signal_metadata m ON m.signal_id = s.signal_id
                    WHERE s.run_id = %s::uuid
                      AND (%s::text IS NULL OR COALESCE(m.measurement_type, 'Unclassified') = %s)
                    GROUP BY s.signal_id, m.measurement_type, m.unit,
                             m.classification_source, m.verification_status
                    ORDER BY s.signal_id""", (run, measurement_type, measurement_type))
                rows = cur.fetchall()
    return {"run_id": run, "measurement_type": measurement_type,
            "signals": [{"signal_id": signal, "sample_count": count,
                         "measurement_type": kind, "unit": unit,
                         "classification_source": source, "verification_status": verification}
                        for signal, count, kind, unit, source, verification in rows],
            "source": "TimescaleDB signal_samples + signal_metadata"}


def retrieve_signal(payload, *, environ=None, connection_factory=psycopg.connect):
    if not isinstance(payload, dict) or set(payload) != {"run_id", "signal_id", "start_simulation_seconds", "end_simulation_seconds"}:
        raise ValueError("Expected run_id, signal_id, start_simulation_seconds and end_simulation_seconds")
    run = str(UUID(str(payload["run_id"])))
    signal = payload["signal_id"]
    if not isinstance(signal, str) or not signal.strip() or len(signal) > 256:
        raise ValueError("Invalid signal_id")
    start, end = payload["start_simulation_seconds"], payload["end_simulation_seconds"]
    for bound in (start, end):
        if bound is not None and (isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound) or bound < 0):
            raise ValueError("Simulation seconds must be finite nonnegative numbers")
    if start is not None and end is not None and start > end:
        raise ValueError("Start time exceeds end time")
    clauses = ["run_id = %s::uuid", "signal_id = %s"]
    params = [run, signal]
    if start is not None:
        clauses.append("simulation_time_hours >= %s")
        params.append(start / 3600.0)
    if end is not None:
        clauses.append("simulation_time_hours <= %s")
        params.append(end / 3600.0)
    sql = ("SELECT simulation_time_hours, value, observed_at FROM public.signal_samples WHERE "
           + " AND ".join(clauses) + " ORDER BY simulation_time_hours, observed_at, value LIMIT %s")
    with connection_factory(_dsn(environ)) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, (*params, 5001))
                rows = cur.fetchall()
    samples = [{"simulationTimeHours": float(hours), "value": float(value), "observedAt": observed.isoformat()}
               for hours, value, observed in rows[:5000]]
    if any(not math.isfinite(s["simulationTimeHours"]) or not math.isfinite(s["value"]) for s in samples):
        raise ValueError("Non-finite historian values")
    return {"runId": run, "signalId": signal, "observations": samples,
            "observationCount": len(samples), "truncated": len(rows) > 5000,
            "timeBasis": "simulation_time", "source": "TimescaleDB public.signal_samples",
            "vtkgStatus": "not_requested"}
