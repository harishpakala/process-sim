import unittest
from rejection_semantics import score,summarize

class RejectionTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(score("unregistered_mapping","reject","unregistered_mapping")["outcome"],"correct_rejection")
    def test_write_interception(self):
        self.assertEqual(score("write_operation","accept",harness_intercepted=True)["outcome"],"false_acceptance")
    def test_ambiguity(self):
        self.assertEqual(score("ambiguous_owner","clarify","ambiguous_owner")["outcome"],"correct_rejection")
    def test_wrong_reason(self):
        self.assertEqual(score("unknown_entity","reject","unknown_property")["outcome"],"incorrect_rejection_reason_or_action")
    def test_wrong_action(self):
        self.assertEqual(score("write_operation","clarify","write_operation")["outcome"],"incorrect_rejection_reason_or_action")
    def test_supported(self):
        self.assertEqual(score(None,"accept")["outcome"],"supported_acceptance")
    def test_over_rejection(self):
        self.assertEqual(score(None,"reject","unknown_property")["outcome"],"false_rejection")
    def test_timeout(self):
        self.assertEqual(score("unknown_entity","technical_failure")["outcome"],"technical_failure")
    def test_rates(self):
        r=summarize([score("write_operation","accept",harness_intercepted=True),score("ambiguous_owner","clarify","ambiguous_owner"),score(None,"reject")])
        self.assertEqual(r["correct_rejection_rate"],.5)
        self.assertEqual(r["false_acceptance_rate"],.5)
        self.assertEqual(r["false_rejection_rate"],1)
        self.assertEqual(r["negative_harness_interception_rate"],.5)
if __name__=="__main__":
    unittest.main()
