"""Finite-state properties of implemented SC/CAC decision composition."""
import itertools
import unittest

from process_sim.selira.integrated_contracts import (
    SC_IDS, CAC_IDS, aggregate, conjunction,
)


def results(source_values, fitness_values):
    return ([{"contract": key, "status": value}
             for key, value in zip(SC_IDS, source_values)] +
            [{"contract": key, "status": value}
             for key, value in zip(CAC_IDS, fitness_values)])


class FormalSemanticsTests(unittest.TestCase):
    def test_source_conjunction_exhaustive(self):
        for values in itertools.product(("V", "F", "U"), repeat=len(SC_IDS)):
            with self.subTest(values=values):
                expected = ("F" if "F" in values else
                            "V" if all(v == "V" for v in values) else "U")
                self.assertEqual(conjunction(values), expected)

    def test_consumer_join_exhaustive(self):
        for source in ("V", "F", "U"):
            source_values = {"V": ("V",)*5, "F": ("F","V","V","V","V"),
                             "U": ("U","V","V","V","V")}[source]
            for left, right in itertools.product(("V","F","U","NA"), repeat=2):
                with self.subTest(source=source, left=left, right=right):
                    decision = aggregate(results(source_values, (left,right)))
                    self.assertEqual(decision["sourceQualification"], source)
                    for contract, fitness in zip(CAC_IDS, (left,right)):
                        expected = ("NA" if fitness == "NA" else
                                    "F" if source == "F" or fitness == "F" else
                                    "V" if source == "V" and fitness == "V" else "U")
                        self.assertEqual(decision["consumers"][contract]["decision"], expected)
                        self.assertFalse(decision["consumers"][contract]["accepted"])
                        self.assertFalse(decision["consumers"][contract]["authorization"])
                    self.assertFalse(decision["authorization"])
                    self.assertEqual(decision["engineeringCertification"], "U")

    def test_unknown_cannot_be_upgraded_by_verified_consumer(self):
        decision = aggregate(results(("V","V","U","V","V"), ("V","V")))
        self.assertEqual(decision["sourceQualification"], "U")
        self.assertTrue(all(v["decision"] == "U"
                            for v in decision["consumers"].values()))

    def test_out_of_scope_does_not_erase_source_failure(self):
        decision = aggregate(results(("F","V","V","V","V"), ("NA","V")))
        self.assertEqual(decision["sourceQualification"], "F")
        self.assertEqual(decision["consumers"]["CAC-01"]["decision"], "NA")
        self.assertEqual(decision["consumers"]["CAC-02"]["decision"], "F")
        self.assertFalse(decision["authorization"])

    def test_invalid_or_empty_source_conjunction_unknown(self):
        self.assertEqual(conjunction([]), "U")
        self.assertEqual(conjunction(["V","INVALID"]), "U")


if __name__ == "__main__":
    unittest.main()
