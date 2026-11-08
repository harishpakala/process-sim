"""Immutable physical EBOM revision snapshots built only from reviewed installation evidence.

Each promoted component is the ECAD source object, not a merged DEXPI/ECAD identity.
"""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from process_sim.api import engineering_reviews as audit

BOM = audit.ROOT / "examples/aas/tep_engineering_bom_instance.json"
EQUIPMENT = {"ASM-REACTOR","ASM-SEPARATOR","ASM-STRIPPER","ASM-CONDENSER","ASM-COMPRESSOR"}

def _items():
    raw=json.loads(BOM.read_text(encoding="utf-8"))
    return {v["BOMItemId"]:v for x in raw["submodelElements"][1]["value"]
            for v in [{p["idShort"]:p["value"] for p in x["value"]}]}

def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS physical_bom_revisions (
      revision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, author TEXT NOT NULL,
      rationale TEXT NOT NULL, snapshot_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL UNIQUE
    )""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS prevent_bom_revision_update
      BEFORE UPDATE ON physical_bom_revisions BEGIN SELECT RAISE(ABORT, 'immutable BOM revision'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS prevent_bom_revision_delete
      BEFORE DELETE ON physical_bom_revisions BEGIN SELECT RAISE(ABORT, 'immutable BOM revision'); END""")

def list_revisions():
    with audit._LOCK, audit._connection() as db:
        _init(db)
        rows=db.execute("SELECT revision_id,created_at,author,rationale,snapshot_json,snapshot_hash FROM physical_bom_revisions ORDER BY rowid").fetchall()
        result=[]
        for row in rows:
            snapshot=json.loads(row["snapshot_json"])
            valid=hashlib.sha256(row["snapshot_json"].encode()).hexdigest()==row["snapshot_hash"]
            result.append({"revisionId":row["revision_id"],"createdAt":row["created_at"],"author":row["author"],
                           "rationale":row["rationale"],"snapshotHash":row["snapshot_hash"],
                           "integrityValid":valid,"snapshot":snapshot})
        return {"revisions":result}

def create_revision(body):
    if not isinstance(body,dict):
        raise ValueError("JSON object required")
    author=body.get("author")
    rationale=body.get("rationale")
    assignments=body.get("assignments")
    if not isinstance(author,str) or not author.strip() or len(author)>200:
        raise ValueError("Author is required")
    if not isinstance(rationale,str) or not rationale.strip() or len(rationale)>4000:
        raise ValueError("Revision rationale is required")
    if not isinstance(assignments,list) or not assignments or len(assignments)>79:
        raise ValueError("Nonempty assignments list required (maximum 79)")
    items=_items()
    registry=audit._registry()
    with audit._LOCK, audit._connection() as db:
        db.execute("BEGIN IMMEDIATE")
        _init(db)
        events=[dict(r) for r in db.execute("SELECT * FROM engineering_review_events ORDER BY sequence")]
        if not audit.verify_chain(events)["valid"]:
            raise ValueError("Audit integrity failed; refusing BOM promotion")
        by_id={e["event_id"]:e for e in events}
        latest={}
        for event in events:
            if event["review_kind"]=="PHYSICAL_MEMBERSHIP":
                latest[event["relationship_id"]]=event
        promoted=[]
        seen=set()
        for assignment in assignments:
            if not isinstance(assignment,dict):
                raise ValueError("Invalid assignment")
            item_id=assignment.get("bomItemId")
            event_id=assignment.get("evidenceEventId")
            if not isinstance(item_id,str) or item_id in seen:
                raise ValueError("Duplicate or invalid BOM item")
            seen.add(item_id)
            item=items.get(item_id)
            event=by_id.get(event_id)
            if item is None or event is None:
                raise ValueError("Unknown BOM item or evidence event")
            relation=registry.get(event["relationship_id"])
            if relation is None or item["SourceDomain"]!="ECAD" or item["EngineeringReference"]!=relation["targetReference"]:
                raise ValueError("Evidence does not identify this ECAD source item")
            if event["review_kind"]!="PHYSICAL_MEMBERSHIP" or event["decision"]!="VERIFIED_PHYSICAL_MEMBERSHIP":
                raise ValueError("Only approved physical-membership evidence can be promoted")
            if latest[event["relationship_id"]]["event_id"]!=event_id:
                raise ValueError("Physical-membership approval has been superseded")
            if event["physical_parent"] not in EQUIPMENT or event["physical_parent"]!=relation["scopeAssembly"]:
                raise ValueError("Physical parent does not match approved equipment")
            if item["ParentItemId"] not in ("ASM-UNASSIGNED",event["physical_parent"]):
                raise ValueError("Conflicting canonical physical parent")
            promoted.append({"bomItemId":item_id,"engineeringReference":item["EngineeringReference"],
                             "sourceDomain":"ECAD","physicalParent":event["physical_parent"],
                             "evidenceEventId":event_id,"evidenceReference":event["evidence_reference"],
                             "approvalEventHash":event["event_hash"],
                             "quantityBasis":"ONE_SOURCE_ENGINEERING_OBJECT_NOT_PROCUREMENT_QUANTITY"})
        revision_id="PBOM-"+uuid4().hex[:12].upper()
        created_at=datetime.now(timezone.utc).isoformat()
        snapshot={"revisionId":revision_id,"createdAt":created_at,
                  "baseline":"tep_engineering_bom_instance.json","physicalAssignments":promoted,
                  "identityEquivalenceAsserted":False,
                  "note":"Revision overlay only; canonical source BOM is unchanged"}
        encoded=json.dumps(snapshot,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        db.execute("INSERT INTO physical_bom_revisions VALUES (?,?,?,?,?,?)",
                   (revision_id,created_at,author.strip(),rationale.strip(),encoded,digest))
        return {"revisionId":revision_id,"snapshotHash":digest,"snapshot":snapshot}
