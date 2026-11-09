"""Derive bounded fault-command intervals in simulation time.

These intervals describe recorded operator commands, not verified plant fault
states or causal effects. All intervals are scoped to a single simulation run.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from uuid import UUID

START_ACTION = "inject"
STOP_ACTION = "clear"


def _time(event):
    value = event.get("simulation_time_hours")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid simulation time")
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError("Invalid simulation time")
    return value


def _event_id(event):
    value = event.get("event_id")
    if value is None or not str(value).strip():
        raise ValueError("Missing event identity")
    return str(value)


def derive_fault_command_intervals(run_id, events, *, complete=True):
    """Pair inject/clear commands, retaining anomalies and open intervals.

    Events must represent a complete run history for definitive closure claims.
    When complete=False, intervals are flagged as potentially truncated.
    """
    run = str(UUID(str(run_id)))
    ordered = []
    seen = set()
    for event in events:
        if str(UUID(str(event.get("run_id")))) != run:
            raise ValueError("Mixed simulation runs")
        identity = _event_id(event)
        if identity in seen:
            raise ValueError("Duplicate event identity")
        seen.add(identity)
        action = event.get("action")
        if action not in (START_ACTION, STOP_ACTION):
            raise ValueError("Unsupported fault command action")
        fault = event.get("fault_id")
        if not isinstance(fault, str) or not fault.strip():
            raise ValueError("Missing fault identifier")
        observed = event.get("observed_at")
        if isinstance(observed, datetime):
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError("Naive observation timestamp")
            observed = observed.isoformat()
        elif not isinstance(observed, str):
            raise ValueError("Missing observation timestamp")
        try:
            parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid observation timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Naive observation timestamp")
        ordered.append((_time(event), observed, identity, action, fault))

    ordered.sort(key=lambda item: (item[0], item[1], item[2]))
    active = {}
    intervals = []
    anomalies = []
    for sim_time, observed, identity, action, fault in ordered:
        if action == START_ACTION:
            if fault in active:
                anomalies.append({"type": "DUPLICATE_INJECT", "faultId": fault,
                                  "eventId": identity})
                continue
            active[fault] = (sim_time, observed, identity)
        elif fault not in active:
            anomalies.append({"type": "UNMATCHED_CLEAR", "faultId": fault,
                              "eventId": identity})
        else:
            started, started_at, start_id = active.pop(fault)
            intervals.append({
                "runId": run, "faultId": fault, "startEventId": start_id,
                "endEventId": identity, "startSimulationHours": started,
                "endSimulationHours": sim_time, "startObservedAt": started_at,
                "endObservedAt": observed, "status": "CLOSED",
                "endExclusive": True, "provenance": "RECORDED_OPERATOR_COMMANDS",
                "historyComplete": bool(complete),
            })
    for fault, (started, observed, identity) in active.items():
        intervals.append({
            "runId": run, "faultId": fault, "startEventId": identity,
            "endEventId": None, "startSimulationHours": started,
            "endSimulationHours": None, "startObservedAt": observed,
            "endObservedAt": None, "status": "OPEN_UNCONFIRMED",
            "endExclusive": True, "provenance": "RECORDED_OPERATOR_COMMANDS",
            "historyComplete": bool(complete),
        })
    intervals.sort(key=lambda item: (item["startSimulationHours"], item["startEventId"]))
    return {
        "runId": run, "intervals": intervals, "anomalies": anomalies,
        "historyComplete": bool(complete),
        "interpretation": "Command-derived intervals; not verified physical fault states.",
    }


def classify_observation(interval, simulation_time_hours):
    """Return BEFORE, DURING, AFTER, or UNKNOWN for a command interval."""
    value = float(simulation_time_hours)
    if not isfinite(value) or value < 0:
        raise ValueError("Invalid observation simulation time")
    start = interval["startSimulationHours"]
    end = interval["endSimulationHours"]
    if value < start:
        return "BEFORE"
    if end is not None:
        return "DURING" if value < end else "AFTER"
    return "UNKNOWN" if not interval.get("historyComplete", False) else "DURING_UNCONFIRMED"
