"""Optional TimescaleDB persistence for TEP runs and sampled signals.

Requires psycopg and a PostgreSQL/TimescaleDB instance. A missing database does
not silently turn persistence into success: the historian exposes its error.
"""

# Created: 2026-10-18
# Author: Harish
from __future__ import annotations
import os
from datetime import datetime, timezone

DSN_ENV = "TEP_TIMESCALE_DSN"

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS simulation_runs (
 run_id UUID PRIMARY KEY,
 started_at TIMESTAMPTZ NOT NULL,
 ended_at TIMESTAMPTZ,
 end_reason TEXT
);
CREATE TABLE IF NOT EXISTS fault_events (
 event_id UUID PRIMARY KEY,
 run_id UUID NOT NULL REFERENCES simulation_runs(run_id),
 observed_at TIMESTAMPTZ NOT NULL,
 simulation_time_hours DOUBLE PRECISION NOT NULL,
 action TEXT NOT NULL,
 fault_id TEXT NOT NULL,
 fault_type TEXT,
 target TEXT,
 magnitude DOUBLE PRECISION,
 event_source TEXT NOT NULL DEFAULT 'operator_command',
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS fault_events_run_time ON fault_events (run_id, observed_at);
CREATE TABLE IF NOT EXISTS signal_samples (
 observed_at TIMESTAMPTZ NOT NULL,
 run_id UUID NOT NULL REFERENCES simulation_runs(run_id),
 simulation_time_hours DOUBLE PRECISION NOT NULL,
 signal_id TEXT NOT NULL,
 value DOUBLE PRECISION NOT NULL,
 PRIMARY KEY (observed_at, run_id, signal_id)
);
SELECT create_hypertable('signal_samples','observed_at',if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS samples_run_signal_time ON signal_samples
 (run_id, signal_id, simulation_time_hours DESC);
"""

def connect():
    import psycopg
    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        raise RuntimeError(f"{DSN_ENV} is not configured")
    return psycopg.connect(dsn, connect_timeout=5)

def initialize():
    with connect() as conn:
        conn.execute(SCHEMA, prepare=False)

def begin_run(run_id, started_at):
    with connect() as conn:
        conn.execute("INSERT INTO simulation_runs(run_id, started_at) VALUES (%s,%s) ON CONFLICT DO NOTHING", (run_id, started_at))

def end_run(run_id, reason):
    with connect() as conn:
        conn.execute("UPDATE simulation_runs SET ended_at=%s,end_reason=%s WHERE run_id=%s AND ended_at IS NULL", (datetime.now(timezone.utc), reason, run_id))

def append_snapshot(run_id, sample):
    observed_at = datetime.now(timezone.utc)
    rows = [(observed_at, run_id, sample["time"], f"XMEAS{i}", float(value))
            for i,value in enumerate(sample["measurements"],1)]
    rows += [(observed_at, run_id, sample["time"], f"XMV{i}", float(value))
             for i,value in enumerate(sample["manipulatedVariables"],1)]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO signal_samples(observed_at,run_id,simulation_time_hours,signal_id,value) VALUES (%s,%s,%s,%s,%s)", rows)

def query_samples(run_id, signal_id, limit=1000):
    with connect() as conn:
        return conn.execute(
            """SELECT simulation_time_hours, value, observed_at FROM (
                 SELECT simulation_time_hours, value, observed_at
                 FROM signal_samples WHERE run_id=%s AND signal_id=%s
                 ORDER BY observed_at DESC LIMIT %s
               ) recent ORDER BY observed_at""",
            (run_id, signal_id, limit),
        ).fetchall()

def append_fault_event(event):
    """Insert a successful operator command; event_id prevents duplicates."""
    import json
    with connect() as conn:
        conn.execute(
            """INSERT INTO fault_events
            (event_id,run_id,observed_at,simulation_time_hours,action,fault_id,
             fault_type,target,magnitude,event_source,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (event_id) DO NOTHING""",
            (event["event_id"], event["run_id"], event["observed_at"],
             event["simulation_time_hours"], event["action"], event["fault_id"],
             event.get("fault_type"), event.get("target"), event.get("magnitude"),
             event.get("event_source", "operator_command"),
             json.dumps(event.get("metadata", {}))),
        )

def query_fault_events(run_id, limit=500):
    with connect() as conn:
        rows = conn.execute(
            """SELECT event_id,run_id,observed_at,simulation_time_hours,action,
                      fault_id,fault_type,target,magnitude,event_source,metadata
               FROM fault_events WHERE run_id=%s ORDER BY observed_at DESC LIMIT %s""",
            (run_id, limit),
        ).fetchall()
    fields = ("event_id","run_id","observed_at","simulation_time_hours","action",
              "fault_id","fault_type","target","magnitude","event_source","metadata")
    return [dict(zip(fields, row)) for row in reversed(rows)]

def query_runs(limit=100):
    """List runs with measurement and fault counts; newest first."""
    if not 1 <= limit <= 500:
        raise ValueError("Limit must be 1..500")
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.run_id, r.started_at, r.ended_at, r.end_reason,
                      COALESCE(s.sample_count, 0), COALESCE(f.fault_count, 0)
               FROM (SELECT * FROM simulation_runs ORDER BY started_at DESC LIMIT %s) r
               LEFT JOIN LATERAL (
                   SELECT count(*) AS sample_count FROM signal_samples
                   WHERE run_id=r.run_id
               ) s ON true
               LEFT JOIN LATERAL (
                   SELECT count(*) AS fault_count FROM fault_events
                   WHERE run_id=r.run_id
               ) f ON true
               ORDER BY r.started_at DESC, r.run_id DESC""",
            (limit,),
        ).fetchall()
    return [
        {"runId": str(run_id), "startedAt": started.isoformat(),
         "endedAt": ended.isoformat() if ended else None,
         "endReason": reason, "sampleCount": samples, "faultEventCount": faults}
        for run_id, started, ended, reason, samples, faults in rows
    ]
