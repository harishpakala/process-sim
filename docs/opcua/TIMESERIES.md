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

## Phase 3: persistent fault command history

Pull the latest main branch and **restart the Python API** with the same
`TEP_TIMESCALE_DSN` used for Phase 1. The historian runs the idempotent
schema initialization, adding `fault_events` to the existing database.
Alternatively, initialize explicitly:

```powershell
$env:PYTHONPATH="src"
python -c "from process_sim.api.timeseries import initialize; initialize()"
```

Successful operator `inject`, `clear`, and `clear_all` commands are recorded
with their historian `run_id`, simulation time, UTC observation time, fault
identifier and target. For `clear_all`, one clear event is recorded per
previously listed fault. A database failure does not undo an already executed
OPC UA command; the API includes a `warning` in its successful response.

Query the database:

```sql
SELECT run_id, fault_id, action, target, simulation_time_hours, observed_at
FROM fault_events ORDER BY observed_at DESC LIMIT 30;
```

Or call
`GET /api/simulation/fault-events/history?runId=<uuid>&limit=500`.
The existing `/api/simulation/fault-events` endpoint remains a process-local
buffer for the current Vue dashboard.

**Limitations:** These events represent confirmed operator commands, not
automatically observed fault expiry or inferred physical effects. A command
that succeeds while OPC UA snapshot timestamp retrieval fails cannot be
persisted by this version. A missing historian run ID or database outage
causes a warning and no persistent record; there is no retry queue. The
historian's run ID is sampled asynchronously, so a reset concurrent with a
fault command can result in incorrect run attribution. Cross-process run
recovery and fully transactional event acquisition are future work.

## Phase 4: import semantic provenance into GraphDB

The endpoint `GET /api/semantic/run?runId=<uuid>` generates RDF/Turtle for
a stored run, its recorded signal identifiers, and its fault command events.
This is an **export**, not an automatic GraphDB import.

To load the verified run into the existing `AAS` repository, use GraphDB
Workbench at `http://localhost:7200`: open **Import → RDF → Upload RDF
files**, select the downloaded Turtle file, and choose the named graph
`https://w3id.org/tep-nexus/graph/temporal-provenance`. Import into a
named graph rather than the default graph to avoid mixing the new run
provenance with the existing asset triples.

To save the RDF export from PowerShell:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/semantic/run?runId=892c05d7-6ab3-4a33-8ee8-67a835fc6c72" -OutFile "tep-run.ttl"
```

Then verify in GraphDB Workbench SPARQL:

```sparql
PREFIX tep: <https://w3id.org/tep-nexus/ontology/>
SELECT ?run (COUNT(DISTINCT ?event) AS ?eventCount)
WHERE {
 GRAPH <https://w3id.org/tep-nexus/graph/temporal-provenance> {
   ?run a tep:SimulationRun .
   OPTIONAL { ?run tep:hasFaultEvent ?event }
 }
}
GROUP BY ?run
```

This RDF currently asserts **signal identifiers** but does not claim
that a particular GraphDB engineering asset maps to those signals.
Inspect existing asset-to-signal mapping triples before adding links.

## Automatic GraphDB synchronization

When `TEP_TIMESCALE_DSN` is configured, the Python API starts a background
GraphDB synchronization worker by default. It checks the TimescaleDB run list
every 15 seconds (`TEP_GRAPH_SYNC_SECONDS` overrides this). Each run's
metadata and fault events are exported to a dedicated named graph:
`https://w3id.org/tep-nexus/graph/temporal-provenance/run/<run-id>`.

The worker uses RDF4J's statements endpoint with HTTP PUT, replacing the
specific run graph instead of appending duplicate triples. This also
backfills existing runs after startup. A GraphDB failure does not interrupt
OPC UA acquisition; it is retried at the next polling interval. The status
endpoint is `GET /api/semantic/sync/status` and reports `enabled`,
`lastRunId`, `lastSuccess`, and `error`.

Use `$env:TEP_GRAPH_SYNC="0"` to disable automatic writes to GraphDB.
For a custom GraphDB repository set `GRAPHDB_SPARQL_ENDPOINT` (default:
`http://localhost:7200/repositories/AAS`). GraphDB must be running and
the repository must permit updates.

**Scope:** The sync publishes run provenance, signal identifiers and fault
command events, not high-frequency sensor readings or inferred asset
relationships. It currently re-exports all runs every interval, which is
simple and robust for small development datasets but not optimized for large
histories. Runs with over 5000 events are truncated by the current exporter.
Per-run graphs are separate from the earlier manual-import example graph.
