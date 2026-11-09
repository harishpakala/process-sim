"""Physical BOM revision promotion regression checks."""

# Created: 2026-10-23
# Author: Harish
import sqlite3
import tempfile
import unittest
from pathlib import Path
from process_sim.api import engineering_reviews as audit, physical_bom

class PhysicalBomRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original=audit.DATABASE
        audit.DATABASE=Path(self.tmp.name)/"reviews.sqlite3"
        self.relation=next(r for r in audit._registry().values() if r["scopeAssembly"]!="ASM-ROOT")
        self.item=next(i for i in physical_bom._items().values() if i["SourceDomain"]=="ECAD" and i["EngineeringReference"]==self.relation["targetReference"])
    def tearDown(self):
        audit.DATABASE=self.original
        self.tmp.cleanup()
    def test_promotion_requires_specific_latest_approved_event(self):
        request={"author":"engineer","rationale":"Installation drawing checked",
                 "assignments":[{"bomItemId":self.item["BOMItemId"],"evidenceEventId":"missing"}]}
        with self.assertRaises(ValueError):
            physical_bom.create_revision(request)
        review={"relationshipId":self.relation["relationshipId"],"reviewKind":"PHYSICAL_MEMBERSHIP",
                "decision":"VERIFIED_PHYSICAL_MEMBERSHIP","reviewer":"engineer",
                "evidenceReference":"drawing A rev 1","notes":"Installation shown on drawing",
                "physicalParent":self.relation["scopeAssembly"],"installationEvidenceConfirmed":True}
        event=audit.append_event(review)["event"]
        request["assignments"][0]["evidenceEventId"]=event["event_id"]
        revision=physical_bom.create_revision(request)
        self.assertEqual(revision["snapshot"]["physicalAssignments"][0]["bomItemId"],self.item["BOMItemId"])
        self.assertFalse(revision["snapshot"]["identityEquivalenceAsserted"])
        self.assertTrue(physical_bom.list_revisions()["revisions"][0]["integrityValid"])
        with audit._connection() as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM physical_bom_revisions")
        review.update(decision="NEEDS_EVIDENCE",physicalParent="")
        audit.append_event(review)
        with self.assertRaises(ValueError):
            physical_bom.create_revision(request)
    def test_cannot_promote_wrong_source_item(self):
        relation=self.relation
        event=audit.append_event({"relationshipId":relation["relationshipId"],"reviewKind":"PHYSICAL_MEMBERSHIP",
           "decision":"VERIFIED_PHYSICAL_MEMBERSHIP","reviewer":"engineer","evidenceReference":"drawing",
           "notes":"Checked","physicalParent":relation["scopeAssembly"],"installationEvidenceConfirmed":True})["event"]
        wrong=next(i for i in physical_bom._items().values() if i["SourceDomain"]=="DEXPI")
        with self.assertRaises(ValueError):
            physical_bom.create_revision({"author":"engineer","rationale":"wrong source","assignments":[{"bomItemId":wrong["BOMItemId"],"evidenceEventId":event["event_id"]}]})

if __name__=="__main__":
    unittest.main()
