"""OPC UA historian with run identity and optional TimescaleDB persistence."""

# Created: 2026-10-17
# Author: Harish
from __future__ import annotations
import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from threading import Event, Lock, Thread
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
_stop_event = Event()
_worker = None

def _run():
    global _latest, _error, _storage_error, _run_id, _last_time
    global _last_running, _persisted_run, _storage_ready
    from process_sim.api.opcua_client import snapshot
    enabled = bool(os.environ.get("TEP_TIMESCALE_DSN"))
    if enabled:
        from process_sim.api import timeseries as store
    while not _stop_event.is_set():
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
        _stop_event.wait(2)

def start():
    global _started, _worker
    with _lock:
        if _started:
            return
        _stop_event.clear()
        _worker = Thread(target=_run, name="tep-historian", daemon=True)
        _started = True
        _worker.start()


def stop(timeout=10):
    """Stop polling before finalizing the active persisted run.

    Raise on timeout or database failure rather than falsely reporting completion.
    """
    global _started, _worker, _persisted_run
    with _lock:
        worker = _worker
        _stop_event.set()
    if worker is None:
        return
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError("Historian worker did not stop; run was not finalized")
    with _lock:
        run_id = _persisted_run
    if run_id is not None:
        from process_sim.api import timeseries as store
        store.end_run(run_id, "application_shutdown")
    with _lock:
        _persisted_run = None
        _worker = None
        _started = False

def history():
    with _lock:
        return {"samples": list(_samples), "snapshot": _latest, "error": _error,
                "runId": _run_id, "persistenceEnabled": bool(os.environ.get("TEP_TIMESCALE_DSN")),
                "storageError": _storage_error}
