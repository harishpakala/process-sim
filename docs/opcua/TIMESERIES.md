# Persistent TEP time-series historian (Phase 1 + Phase 2)

The Python API samples the OPC UA simulator every ~2 seconds and keeps a
short rolling buffer for the Vue dashboard. Optionally it writes **all 41 XMEAS
and 12 XMV signals** to TimescaleDB. GraphDB remains the engineering knowledge
graph; the historian does not write RDF.

## Local setup

1. Start the database: `docker compose -f docker-compose.timeseries.yml up -d`.
2. Install Python dependencies: `pip install -r requirements-opcua.txt -r requirements-timeseries.txt`.
3. Set `TEP_TIMESCALE_DSN` to a PostgreSQL connection string, e.g.
   `postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus`.
   The sample password is **development-only**; override `TEP_DB_PASSWORD`
   and use the matching DSN outside a local workstation.
4. Start the existing OPC UA server, then start the API with
   `PYTHONPATH=src python -m process_sim.api.server`.
   The API initializes the schema automatically when the DSN is configured.
5. Check `GET /api/simulation/history`: `runId`,
   `persistenceEnabled`, and `storageError` report the current state.
6. Query a signal with
   `GET /api/simulation/series?runId=<uuid>&signal=XMEAS9&limit=1000`.

On Windows PowerShell use `$env:TEP_TIMESCALE_DSN="postgresql://..."`
and `$env:PYTHONPATH="src"` before launching the API.

## Schema and run semantics

- `simulation_runs(run_id, started_at, ended_at, end_reason)` stores run
  identity and provenance.
- `signal_samples(observed_at, run_id, simulation_time_hours, signal_id, value)`
  is a TimescaleDB hypertable, indexed for run/signal queries.
- `observed_at` is UTC wall-clock acquisition time; `simulation_time_hours`
  is the simulator's clock. These are **not interchangeable**.
- A run ID is assigned on the first successful historian observation and
  renewed when the simulation clock moves backwards (reset).
- Stopping/starting without resetting retains the same run ID.
- Run IDs are currently owned by the Python API process. Restarting that
  process creates a new run even if the simulator has not reset.
- Samples are recorded when the simulation time advances. Paused/stopped
  repeated values are not duplicated.

## Current limitations

The writer is synchronous and uses a new database connection per sample
batch; optimize with pooling/batching for higher acquisition rates. The API
keeps collecting into its in-memory buffer when TimescaleDB is unavailable
and exposes the storage error; **missed samples are not backfilled**. Schema
initialization requires permission to install the TimescaleDB extension.
There is no persistent fault-event store, temporal RDF model, retention policy,
or cross-process run recovery yet. Those belong to subsequent phases.

The API is loopback-bound by default and has no authentication. Do not expose
it or the sample database credentials to untrusted networks.
