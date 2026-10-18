"""In-memory, process-local log of successful operator fault commands."""
from __future__ import annotations
from collections import deque
from threading import Lock
from datetime import datetime, timezone
from uuid import uuid4
import os

_events = deque(maxlen=500)
_lock = Lock()
_sequence = 0


def record(action: str, fault_id: str, simulation_time_hours: float, target: str = "",
           *, run_id=None, fault_type=None, magnitude=None, metadata=None):
    global _sequence
    event = {"event_id": str(uuid4()), "run_id": run_id,
             "observed_at": datetime.now(timezone.utc).isoformat(),
             "action": action, "fault_id": fault_id, "target": target,
             "fault_type": fault_type, "magnitude": magnitude,
             "simulation_time_hours": float(simulation_time_hours),
             "event_source": "operator_command", "metadata": metadata or {}}
    warning = None
    if os.environ.get("TEP_TIMESCALE_DSN"):
        if not run_id:
            warning = "No active historian run ID; event not persisted"
        else:
            try:
                from process_sim.api.timeseries import append_fault_event
                append_fault_event(event)
            except Exception as exc:
                warning = f"Fault event storage failed: {exc}"
    with _lock:
        _sequence += 1
        _events.append({**event, "sequence": _sequence})
    return warning


def list_events() -> list[dict]:
    with _lock:
        return list(_events)
