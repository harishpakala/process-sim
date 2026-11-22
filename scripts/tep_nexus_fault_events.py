"""Read-only, run-scoped recorded fault-command evidence from TimescaleDB."""
from uuid import UUID


def fetch_recorded_commands(dsn, run_id, start_seconds=None, end_seconds=None):
    """Return source events within the requested simulation-time window.

    A command is a recorded event marker, not proof of a physical fault.
    """
    import psycopg
    run = str(UUID(str(run_id)))
    clauses = ["run_id = %s::uuid"]
    params = [run]
    if start_seconds is not None:
        clauses.append("simulation_time_hours >= %s")
        params.append(float(start_seconds) / 3600.0)
    if end_seconds is not None:
        clauses.append("simulation_time_hours <= %s")
        params.append(float(end_seconds) / 3600.0)
    sql = ("""SELECT event_id, action, simulation_time_hours, observed_at,
                     fault_id, fault_type, target, magnitude, event_source
              FROM public.fault_events WHERE """ + " AND ".join(clauses) +
           " ORDER BY simulation_time_hours, observed_at, event_id")
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    return [{
        "event_id": str(row[0]), "action": row[1],
        "simulation_time_hours": row[2],
        "observed_at": row[3].isoformat() if row[3] is not None else None,
        "fault_id": row[4], "fault_type": row[5], "target": row[6],
        "magnitude": row[7], "event_source": row[8],
    } for row in rows]
