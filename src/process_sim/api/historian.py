"""OPC UA historian with run identity and optional TimescaleDB persistence."""

# Created: 2026-10-17
# Author: Harish
from __future__ import annotations
import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from threading import Lock, Thread
from time import sleep
from uuid import uuid4

_lock = Lock()
_samples = deque(maxlen=1800)
_latest = None
_error = None
_storage_error = None
_started = False
_run_id = None
_last_time = None
_last_running = None
_persisted_run = None
_storage_ready = False

def _run():
    global _latest, _error, _storage_error, _run_id, _last_time
    global _last_running, _persisted_run, _storage_ready
    from process_sim.api.opcua_client import snapshot
    enabled = bool(os.environ.get("TEP_TIMESCALE_DSN"))
    if enabled:
        from process_sim.api import timeseries as store
    while True:
        try:
            result = asyncio.run(snapshot())
            sim = result["simulation"]
            time = float(sim["TimeHours"])
            running = bool(sim["Running"])
            now = datetime.now(timezone.utc)
            with _lock:
                # A backward clock jump indicates reset. A stopped->running
                # transition starts a run only when no run exists yet.
                reset = _last_time is not None and time < _last_time
                if _run_id is None or reset:
                    old_run = _run_id
                    _run_id = str(uuid4())
                    _samples.clear()
                    _persisted_run = None
                else:
                    old_run = None
                run_id = _run_id
                _last_time = time
                _last_running = running
                sample = {"time": time, "measurements": result["measurements"],
                          "manipulatedVariables": result["manipulatedVariables"],
                          "runId": run_id}
                fresh = not _samples or time != _samples[-1]["time"]
                if fresh:
                    _samples.append(sample)
                _latest = {**result, "runId": run_id}
                _error = None
            if enabled:
                try:
                    if not _storage_ready:
                        store.initialize()
                        _storage_ready = True
                    if old_run:
                        store.end_run(old_run, "simulation_reset")
                    if _persisted_run != run_id:
                        store.begin_run(run_id, now)
                        _persisted_run = run_id
                    if fresh:
                        store.append_snapshot(run_id, sample)
                    _storage_error = None
                except Exception as exc:
                    _storage_error = str(exc)
                    # Retry setup / run registration on next cycle.
                    _storage_ready = False
                    _persisted_run = None
        except Exception as exc:
            with _lock:
                _error = str(exc)
                _latest = None
        sleep(2)

def start():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    Thread(target=_run, name="tep-historian", daemon=True).start()

def history():
    with _lock:
        return {"samples": list(_samples), "snapshot": _latest, "error": _error,
                "runId": _run_id, "persistenceEnabled": bool(os.environ.get("TEP_TIMESCALE_DSN")),
                "storageError": _storage_error}
