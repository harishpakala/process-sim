"""Automatic, idempotent semantic provenance synchronization to GraphDB.

The worker periodically rebuilds each run's RDF from authoritative TimescaleDB
records and replaces only that run's dedicated named graph.
"""

# Created: 2026-10-18
# Author: Harish
from __future__ import annotations
import os
from threading import Thread, Lock
from time import sleep
from urllib.parse import quote
from urllib.request import Request, urlopen

_lock = Lock()
_started = False
_state = {"enabled": False, "lastRunId": None, "lastSuccess": None, "error": None}
BASE_GRAPH = "https://w3id.org/tep-nexus/graph/temporal-provenance/run/"
DEFAULT_REPOSITORY = "http://localhost:7200/repositories/AAS"

def status():
    with _lock:
        return dict(_state)

def _set(**values):
    with _lock:
        _state.update(values)

def _sync_one(run_id):
    from process_sim.api.temporal_rdf import export_run
    rdf = export_run(run_id).encode("utf-8")
    endpoint = os.environ.get("GRAPHDB_SPARQL_ENDPOINT", DEFAULT_REPOSITORY).rstrip("/")
    # GraphDB RDF4J statements endpoint: PUT replaces this graph atomically.
    url = endpoint + "/statements?context=" + quote("<" + BASE_GRAPH + str(run_id) + ">", safe="")
    request = Request(url, data=rdf, method="PUT", headers={"Content-Type": "text/turtle; charset=utf-8"})
    with urlopen(request, timeout=15) as response:
        response.read()

def sync_once():
    from datetime import datetime, timezone
    from process_sim.api.timeseries import connect
    with connect() as conn:
        runs = conn.execute("SELECT run_id FROM simulation_runs ORDER BY started_at").fetchall()
    for (run_id,) in runs:
        _sync_one(run_id)
        _set(lastRunId=str(run_id), lastSuccess=datetime.now(timezone.utc).isoformat(), error=None)
    return len(runs)

def _loop():
    interval = max(5, int(os.environ.get("TEP_GRAPH_SYNC_SECONDS", "15")))
    while True:
        try:
            sync_once()
            _set(error=None)
        except Exception as exc:
            _set(error=str(exc))
        sleep(interval)

def start():
    global _started
    enabled = bool(os.environ.get("TEP_TIMESCALE_DSN")) and os.environ.get("TEP_GRAPH_SYNC", "1") == "1"
    _set(enabled=enabled)
    if not enabled:
        return
    with _lock:
        if _started:
            return
        _started = True
    Thread(target=_loop, name="tep-graph-sync", daemon=True).start()
