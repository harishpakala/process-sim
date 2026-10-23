"""Regression checks for server-backed append-only review history."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from process_sim.api import engineering_reviews as reviews

class EngineeringReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original=reviews.DATABASE
        reviews.DATABASE=Path(self.tmp.name)/"review.sqlite3"
        self.relationship=next(iter(reviews._registry()))

    def tearDown(self):
        reviews.DATABASE=self.original
        self.tmp.cleanup()

    def body(self, **changes):
        return dict(relationshipId=self.relationship,reviewKind="FUNCTIONAL_CORRESPONDENCE",
                    decision="NEEDS_EVIDENCE",reviewer="reviewer-1",
                    evidenceReference="drawing-1 rev A",notes="Further engineering confirmation needed",**changes)

    def test_append_only_and_hash_chain(self):
        a=reviews.append_event(self.body())["event"]
        b=reviews.append_event(self.body())["event"]
        self.assertEqual((a["sequence"],b["sequence"]),(1,2))
        self.assertEqual(b["previous_hash"],a["event_hash"])
        self.assertTrue(reviews.list_events()["integrity"]["valid"])
        with reviews._connection() as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM engineering_review_events WHERE sequence=1")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE engineering_review_events SET reviewer='tamper' WHERE sequence=1")

    def test_physical_verification_requires_installation_evidence(self):
        relation=reviews._registry()[self.relationship]
        parent=relation["scopeAssembly"]
        if parent=="ASM-ROOT":
            self.skipTest("First candidate has plant scope")
        base=self.body()
        base.update(reviewKind="PHYSICAL_MEMBERSHIP",decision="VERIFIED_PHYSICAL_MEMBERSHIP",physicalParent=parent)
        with self.assertRaises(ValueError):
            reviews.append_event(base)
        base["installationEvidenceConfirmed"]=True
        result=reviews.append_event(base)["event"]
        self.assertEqual(result["physical_parent"],parent)
        self.assertTrue(reviews.list_events()["integrity"]["valid"])

    def test_invalid_relationship_rejected(self):
        body=self.body()
        body["relationshipId"]="REL-DOES-NOT-EXIST"
        with self.assertRaises(ValueError):
            reviews.append_event(body)

if __name__=="__main__":
    unittest.main()
