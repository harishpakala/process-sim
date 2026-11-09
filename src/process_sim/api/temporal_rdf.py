"""Deterministic RDF/Turtle export of TimescaleDB run provenance.

High-frequency measurements remain in TimescaleDB. This module exports only
run and fault event metadata; no unverified asset-to-signal links are asserted.
"""

# Created: 2026-10-18
# Author: Harish
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from urllib.parse import quote

BASE = "https://w3id.org/tep-nexus/"

def _literal(value):
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return '"' + text + '"'

def _date(value):
    if isinstance(value, datetime):
        value = value.isoformat()
    return _literal(value) + "^^xsd:dateTime"

def export_run(run_id):
    from process_sim.api.timeseries import connect, query_fault_events
    uid = str(UUID(str(run_id)))
    with connect() as conn:
        run = conn.execute(
            "SELECT started_at, ended_at, end_reason FROM simulation_runs WHERE run_id=%s",
            (uid,),
        ).fetchone()
        if run is None:
            raise LookupError("Simulation run not found")
        signals = [r[0] for r in conn.execute(
            "SELECT DISTINCT signal_id FROM signal_samples WHERE run_id=%s ORDER BY signal_id",
            (uid,),
        ).fetchall()]
    events = query_fault_events(uid, 5000)
    lines = [
        "@prefix tep: <" + BASE + "ontology/> .",
        "@prefix run: <" + BASE + "run/> .",
        "@prefix event: <" + BASE + "event/> .",
        "@prefix signal: <" + BASE + "signal/> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        "run:" + uid + " a tep:SimulationRun ;",
        "  tep:runId " + _literal(uid) + " ;",
        "  tep:startedAt " + _date(run[0]) + " ;",
    ]
    if run[1]:
        lines.append("  tep:endedAt " + _date(run[1]) + " ;")
    if run[2]:
        lines.append("  tep:endReason " + _literal(run[2]) + " ;")
    lines[-1] = lines[-1][:-2] + " ." if lines[-1].endswith(" ;") else lines[-1]
    for name in signals:
        if not (name.startswith("XMEAS") or name.startswith("XMV")):
            continue
        lines.extend([
            "run:" + uid + " tep:hasRecordedSignal signal:" + quote(name, safe="") + " .",
            "signal:" + quote(name, safe="") + " a tep:OperationalSignal ; tep:signalId " + _literal(name) + " .",
        ])
    for e in events:
        eid = str(e["event_id"])
        lines.extend([
            "run:" + uid + " tep:hasFaultEvent event:" + eid + " .",
            "event:" + eid + " a tep:FaultCommandEvent ;",
            "  tep:inSimulationRun run:" + uid + " ;",
            "  tep:faultId " + _literal(e["fault_id"]) + " ;",
            "  tep:action " + _literal(e["action"]) + " ;",
            "  tep:simulationTimeHours " + _literal(e["simulation_time_hours"]) + "^^xsd:double ;",
            "  tep:observedAt " + _date(e["observed_at"]) + " .",
        ])
        if e.get("target"):
            lines.append("event:" + eid + " tep:targetIdentifier " + _literal(e["target"]) + " .")
        if e.get("fault_type"):
            lines.append("event:" + eid + " tep:faultType " + _literal(e["fault_type"]) + " .")
        if e.get("magnitude") is not None:
            lines.append("event:" + eid + " tep:magnitude " + _literal(e["magnitude"]) + "^^xsd:double .")
    return "\n".join(lines) + "\n"
