"""Tests for evidence-derived provisional measurement classifications."""
import unittest

from scripts.classify_historian_signals import classify_local_id, proposed_classifications


class ClassificationTests(unittest.TestCase):
    def test_local_id_prefixes(self):
        for local_id, expected in (("TI_101", "Temperature"), ("PI-1101", "Pressure"),
                                   ("LI_102", "Level"), ("FI_107", "Flow"),
                                   ("JI_108", "Energy")):
            self.assertEqual(classify_local_id(local_id), expected)
        self.assertIsNone(classify_local_id("XMEAS9"))
        self.assertIsNone(classify_local_id("TI_101_extra"))

    def test_consistent_cross_domain_mapping(self):
        data = {"DEXPI": {"TI_101": {("asset", "XMEAS9")}},
                "ECAD": {"TI-1101": {("asset", "XMEAS9")}}}
        row = proposed_classifications(data, {"XMEAS9"})[0]
        self.assertEqual(row["measurement_type"], "Temperature")
        self.assertEqual(row["verification_status"], "PROVISIONAL")
        self.assertEqual(len(row["evidence"]), 2)

    def test_conflicting_types_stay_unclassified(self):
        data = {"DEXPI": {"TI_101": {("asset", "XMEAS9")}},
                "ECAD": {"PI-1101": {("asset", "XMEAS9")}}}
        row = proposed_classifications(data, {"XMEAS9"})[0]
        self.assertEqual(row["measurement_type"], "Unclassified")
        self.assertEqual(row["verification_status"], "NOT_VERIFIED")

    def test_unmapped_signal_stays_unclassified(self):
        row = proposed_classifications({"DEXPI": {}, "ECAD": {}}, {"S1"})[0]
        self.assertEqual(row["measurement_type"], "Unclassified")


if __name__ == "__main__":
    unittest.main()
