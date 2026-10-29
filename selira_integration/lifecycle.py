"""SC-01 lifecycle vertical slice: snapshot changes, impact, selective revalidation.

Pure-Python reference engine. Uses source identifiers exactly as serialized; does
not certify product suitability. Caller must attest catalog completeness and rule
authority. Historical records are append-only; production needs transactional RDF
persistence and GraphDB snapshot capture.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json

@dataclass(frozen=True)
class Snapshot:
    revision: str
    # asset URI -> assigned product reference (candidate references excluded)
    assigned: dict[str, str]
    # catalog product URI -> asset identifier
    catalog: dict[str, str]
    complete: bool = True

def check(snapshot: Snapshot, asset: str) -> str:
    if not snapshot.complete:
        return "INDETERMINATE"
    ref = snapshot.assigned.get(asset)
    if ref is None:
        return "NOT_APPLICABLE"
    matches = [p for p, identifier in snapshot.catalog.items() if identifier == ref]
    return "VALIDATED" if len(matches) == 1 else "INVALID"

def detect(before: Snapshot, after: Snapshot) -> list[dict]:
    """LP-01: immutable change records for changed assigned refs and identifiers."""
    events = []
    for kind, old, new in (
        ("assigned", before.assigned, after.assigned),
        ("catalog", before.catalog, after.catalog),
    ):
        for key in sorted(old.keys() | new.keys()):
            if old.get(key) != new.get(key):
                events.append({"kind": kind, "entity": key,
                               "old": old.get(key), "new": new.get(key)})
    if before.complete != after.complete:
        events.append({"kind": "completeness", "entity": "catalog",
                       "old": before.complete, "new": after.complete})
    return events

def impacted(before: Snapshot, after: Snapshot, events: list[dict]) -> set[str]:
    """LP-02/03: match both old and new catalog keys, including duplicate changes."""
    if any(e["kind"] == "completeness" for e in events):
        return set(before.assigned) | set(after.assigned)
    affected = {e["entity"] for e in events if e["kind"] == "assigned"}
    changed_values = {value for e in events if e["kind"] == "catalog"
                      for value in (e["old"], e["new"]) if value is not None}
    for asset in set(before.assigned) | set(after.assigned):
        if before.assigned.get(asset) in changed_values or after.assigned.get(asset) in changed_values:
            affected.add(asset)
    return affected

class Lifecycle:
    """LP-04/05/06 reference engine with JSONL audit, no GraphDB writes."""
    def __init__(self, history_path=None):
        self.current = {}
        self.records = []
        self.history_path = Path(history_path) if history_path else None

    def _record(self, record):
        self.records.append(record)
        if self.history_path:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def initialize(self, snapshot: Snapshot):
        for asset in sorted(snapshot.assigned):
            result = check(snapshot, asset)
            self.current[asset] = result
            self._record({"event": "initial_validation", "asset": asset,
                          "revision": snapshot.revision, "outcome": result,
                          "timestamp": datetime.now(timezone.utc).isoformat()})

    def apply(self, before: Snapshot, after: Snapshot) -> dict:
        if not self.current:
            raise ValueError("Initialize before applying a revision")
        events = detect(before, after)
        affected = impacted(before, after, events)
        prior = dict(self.current)
        for asset in sorted(affected):
            self._record({"event": "pending_revalidation", "asset": asset,
                          "revision": after.revision,
                          "previous_outcome": prior.get(asset),
                          "timestamp": datetime.now(timezone.utc).isoformat()})
        for asset in sorted(affected):
            outcome = check(after, asset)
            if outcome == "NOT_APPLICABLE":
                self.current.pop(asset, None)
            else:
                self.current[asset] = outcome
            self._record({"event": "revalidation", "asset": asset,
                          "revision": after.revision, "outcome": outcome,
                          "previous_outcome": prior.get(asset),
                          "timestamp": datetime.now(timezone.utc).isoformat()})
        # E12: full-revalidation baseline is an oracle, not a production step.
        baseline = {asset: check(after, asset) for asset in after.assigned}
        agreement = baseline == self.current
        unaffected = (set(before.assigned) | set(after.assigned)) - affected
        unchanged = all(prior.get(a) == self.current.get(a) for a in unaffected)
        return {"from_revision": before.revision, "to_revision": after.revision,
                "events": events, "affected": sorted(affected),
                "baseline": baseline, "current": dict(self.current),
                "baseline_agreement": agreement,
                "unaffected_unchanged": unchanged,
                "selective_evaluations": len(affected),
                "full_evaluations": len(after.assigned)}
