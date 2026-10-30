"""Experimental SELiRA engineering evidence checks for a single TEP signal.

Input is a reviewed, revision-scoped evidence snapshot, NOT authenticated GraphDB
proof. This module never upgrades missing or contradictory evidence to VALID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .consumer_policy import authorize_use
from .resolution import resolve_correspondence

_ROLES = ("DEXPI", "ECAD", "PLC", "OPCUA", "TEP")
_UNITS = {
    "pa": ("pressure", 1.0), "kpa": ("pressure", 1000.0),
    "bar": ("pressure", 100000.0), "psi": ("pressure", 6894.757293),
    "k": ("temperature", 1.0), "degc": ("temperature", 1.0),
    "celsius": ("temperature", 1.0),
}


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    status: str
    reasons: tuple[str, ...]
    signal: str | None = None


def _check(snapshot: Mapping, task: Mapping) -> GateDecision:
    if not isinstance(snapshot, Mapping) or not isinstance(task, Mapping):
        return GateDecision(False, "U", ("missing evidence or task",))
    revision = snapshot.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        return GateDecision(False, "U", ("source revision not established",))
    if snapshot.get("lifecycle") != "CURRENT":
        return GateDecision(False, "U", ("assessment not current",))
    if task.get("revision") != revision:
        return GateDecision(False, "U", ("task and evidence revisions differ",))

    paths = snapshot.get("paths")
    if not isinstance(paths, list) or not paths:
        return GateDecision(False, "U", ("no authoritative identity path",))
    if len(paths) != 1:
        return GateDecision(False, "F", ("ambiguous identity paths",))
    path = paths[0]
    if not isinstance(path, Mapping):
        return GateDecision(False, "U", ("invalid identity path",))
    nodes = path.get("nodes")
    if not isinstance(nodes, Mapping) or any(
        not isinstance(nodes.get(role), str) or not nodes[role].strip()
        for role in _ROLES
    ):
        return GateDecision(False, "U", ("incomplete DEXPI/ECAD/PLC/OPCUA/TEP chain",))
    edges = path.get("edges")
    if not isinstance(edges, list) or len(edges) != 4 or any(
        not isinstance(edge, Mapping)
        or edge.get("from") != nodes[_ROLES[i]]
        or edge.get("to") != nodes[_ROLES[i + 1]]
        or not isinstance(edge.get("evidence"), str)
        or not edge["evidence"].strip()
        or edge.get("revision") != revision
        for i, edge in enumerate(edges)
    ):
        return GateDecision(False, "U", ("chain links lack revision-scoped evidence",))

    signal = path.get("signal")
    property_id = task.get("property")
    if not isinstance(signal, str) or not isinstance(property_id, str):
        return GateDecision(False, "U", ("signal or property missing",))
    if signal != task.get("signal") or path.get("property") != property_id:
        return GateDecision(False, "F", ("identity or requested property mismatch",))
    if signal != "XMEAS7":
        return GateDecision(False, "U", ("only XMEAS7 is supported by this experiment",))

    engineering_kind = path.get("engineeringQuantityKind")
    signal_kind = path.get("signalQuantityKind")
    if not engineering_kind or not signal_kind:
        return GateDecision(False, "U", ("quantity kind not evidenced",))
    if engineering_kind != signal_kind:
        return GateDecision(False, "F", ("SC-02 quantity kind mismatch",))

    engineering_unit = str(path.get("engineeringUnit", "")).lower()
    signal_unit = str(path.get("signalUnit", "")).lower()
    if not engineering_unit or not signal_unit:
        return GateDecision(False, "U", ("unit not evidenced",))
    lhs, rhs = _UNITS.get(engineering_unit), _UNITS.get(signal_unit)
    if lhs is None or rhs is None:
        return GateDecision(False, "U", ("unit conversion not established",))
    if lhs[0] != rhs[0] or lhs[0] != engineering_kind:
        return GateDecision(False, "F", ("SC-03 incompatible units",))

    # CAC-01: task-specific evidence fitness, independently of source qualification.
    if task.get("runId") != snapshot.get("runId") or not task.get("runId"):
        return GateDecision(False, "U", ("run provenance missing or mismatched",))
    interval = task.get("interval")
    coverage = snapshot.get("coverage")
    if (not isinstance(interval, list) or len(interval) != 2
            or not isinstance(coverage, list) or len(coverage) != 2
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                       for x in interval + coverage)):
        return GateDecision(False, "U", ("time interval or coverage unavailable",))
    if interval[0] > interval[1] or coverage[0] > coverage[1]:
        return GateDecision(False, "F", ("invalid time interval",))
    if interval[0] < coverage[0] or interval[1] > coverage[1]:
        return GateDecision(False, "F", ("CAC-01 insufficient measurement coverage",))
    evidence_refs = [edge["evidence"] for edge in edges]
    reference = "tep://" + signal
    declaration = {
        "requestedProperty": property_id, "signal": signal,
        "reference": reference, "validationStatus": "validated",
        "applicabilityStatus": "applicable", "evidenceReferences": evidence_refs,
    }
    result = resolve_correspondence(property_id, [reference], [declaration])
    if not authorize_use(result):
        return GateDecision(False, "U", ("resolution or consumer policy denied",))
    return GateDecision(True, "V", (), signal)


def evaluate_engineering_use(snapshot: Mapping, task: Mapping) -> GateDecision:
    """Fail closed on malformed snapshots; never accept user-supplied status alone."""
    try:
        return _check(snapshot, task)
    except (TypeError, ValueError, KeyError, AttributeError):
        return GateDecision(False, "U", ("malformed engineering evidence",))
