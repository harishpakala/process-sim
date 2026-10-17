"""In-memory, process-local log of successful operator fault commands."""
from __future__ import annotations
from collections import deque
from threading import Lock

_events = deque(maxlen=500)
_lock = Lock()
_sequence = 0


def record(action: str, fault_id: str, simulation_time_hours: float, target: str = "") -> None:
    global _sequence
    with _lock:
        _sequence += 1
        _events.append({
            "sequence": _sequence,
            "action": action,
            "fault_id": fault_id,
            "target": target,
            "simulation_time_hours": float(simulation_time_hours),
        })


def list_events() -> list[dict]:
    with _lock:
        return list(_events)
