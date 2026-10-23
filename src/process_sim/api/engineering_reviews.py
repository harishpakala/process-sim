"""Append-only SQLite engineering review events, with hash-linked audit records.

No authentication: reviewer is a self-declared identifier, not an authenticated identity.
Default database is a persistent local file; set PROCESS_SIM_REVIEW_DB for deployment.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "examples/aas/tep_engineering_relationship_registry.json"
DATABASE = Path(os.environ.get("PROCESS_SIM_REVIEW_DB", str(ROOT / "data/engineering_reviews.sqlite3")))
_LOCK = threading.RLock()
DECISIONS = {"ACCEPTED_FUNCTIONAL_CORRESPONDENCE", "REJECTED", "NEEDS_EVIDENCE"}
KINDS = {"FUNCTIONAL_CORRESPONDENCE", "PHYSICAL_MEMBERSHIP"}
MEMBERSHIP_DECISIONS = {"VERIFIED_PHYSICAL_MEMBERSHIP", "REJECTED", "NEEDS_EVIDENCE"}

def _registry():
    return {r["relationshipId"]: r for r in json.loads(REGISTRY.read_text(encoding="utf-8"))["relationships"]}

def _connection():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("""CREATE TABLE IF NOT EXISTS engineering_review_events (
      sequence INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL UNIQUE,
      relationship_id TEXT NOT NULL,
      review_kind TEXT NOT NULL,
      decision TEXT NOT NULL,
      reviewer TEXT NOT NULL,
      evidence_reference TEXT NOT NULL,
      rationale TEXT NOT NULL,
      physical_parent TEXT NOT NULL DEFAULT '',
      recorded_at TEXT NOT NULL,
      previous_hash TEXT NOT NULL,
      event_hash TEXT NOT NULL UNIQUE
    )""")
    return db

def _hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

def list_events():
    with _LOCK, _connection() as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM engineering_review_events ORDER BY sequence")]
    return {"events": rows, "integrity": verify_chain(rows)}

def verify_chain(rows):
    previous="GENESIS"
    for row in rows:
        payload={key:row[key] for key in ("event_id","relationship_id","review_kind","decision","reviewer","evidence_reference","rationale","physical_parent","recorded_at","previous_hash")}
        if row["previous_hash"]!=previous or _hash(payload)!=row["event_hash"]:
            return {"valid": False, "failedSequence":row["sequence"]}
        previous=row["event_hash"]
    return {"valid": True, "eventCount":len(rows), "headHash":previous}

def append_event(body):
    if not isinstance(body,dict):
        raise ValueError("JSON object required")
    relationship_id=body.get("relationshipId")
    relation=_registry().get(relationship_id)
    if relation is None:
        raise ValueError("Unknown relationship ID")
    kind=body.get("reviewKind","FUNCTIONAL_CORRESPONDENCE")
    decision=body.get("decision")
    if kind not in KINDS or decision not in (DECISIONS if kind=="FUNCTIONAL_CORRESPONDENCE" else MEMBERSHIP_DECISIONS):
        raise ValueError("Unsupported review kind or decision")
    reviewer=body.get("reviewer")
    evidence=body.get("evidenceReference")
    rationale=body.get("notes")
    parent=body.get("physicalParent","")
    for value,name,limit in ((reviewer,"reviewer",200),(evidence,"evidenceReference",1000),(rationale,"notes",4000)):
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise ValueError(f"{name} must be a nonempty string (max {limit} characters)")
    if not isinstance(parent,str) or len(parent)>100:
        raise ValueError("Invalid physicalParent")
    if kind=="PHYSICAL_MEMBERSHIP":
        if decision=="VERIFIED_PHYSICAL_MEMBERSHIP":
            if parent not in ("ASM-REACTOR","ASM-SEPARATOR","ASM-STRIPPER","ASM-CONDENSER","ASM-COMPRESSOR"):
                raise ValueError("Verified membership requires a valid equipment assembly")
            if relation["scopeAssembly"]!=parent:
                raise ValueError("Physical parent must match candidate equipment scope")
            if not body.get("installationEvidenceConfirmed"):
                raise ValueError("Explicit installation-evidence confirmation required")
        elif parent:
            raise ValueError("Unverified physical membership must not assign a parent")
    elif parent:
        raise ValueError("Functional review cannot set physical parent")
    with _LOCK, _connection() as db:
        db.execute("BEGIN IMMEDIATE")
        last=db.execute("SELECT event_hash FROM engineering_review_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous=last["event_hash"] if last else "GENESIS"
        payload=dict(event_id=str(uuid4()),relationship_id=relationship_id,review_kind=kind,decision=decision,
                     reviewer=reviewer.strip(),evidence_reference=evidence.strip(),rationale=rationale.strip(),
                     physical_parent=parent,recorded_at=datetime.now(timezone.utc).isoformat(),previous_hash=previous)
        digest=_hash(payload)
        cursor=db.execute("""INSERT INTO engineering_review_events
          (event_id,relationship_id,review_kind,decision,reviewer,evidence_reference,rationale,physical_parent,recorded_at,previous_hash,event_hash)
          VALUES (:event_id,:relationship_id,:review_kind,:decision,:reviewer,:evidence_reference,:rationale,:physical_parent,:recorded_at,:previous_hash,:event_hash)""",
          {**payload,"event_hash":digest})
        return {"event":{**payload,"event_hash":digest,"sequence":cursor.lastrowid}}
