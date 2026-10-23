import unittest
from process_sim.ai.alignment_candidates import alignment_review_queue

class CandidateTests(unittest.TestCase):
    def test_review_queue_is_proposed_only(self):
        rows = alignment_review_queue()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["verificationStatus"] == "proposed" for r in rows))
        self.assertTrue(all(r["propertyTermIrdi"] is None for r in rows))
        self.assertTrue(all(not r["comparisonAuthorized"] for r in rows))

    def test_pressure_properties_remain_distinct(self):
        rows = [r for r in alignment_review_queue() if r["signal"] == "XMEAS7"]
        self.assertEqual({r["catalogProperty"] for r in rows},
                         {"RatedDifferentialPressure", "OperatingPressure", "ProofPressure"})
