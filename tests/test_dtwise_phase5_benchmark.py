"""Phase 5 evaluation must not claim correctness from compilation alone."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from dtwise_phase5_benchmark import evaluate
class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.case={"id":"x","question":"q","expected_route":"ebom_v2_catalog","expected_engineering_ids":["A"]}
    def test_matching_ids(self):
        r=evaluate(self.case,{"route":"ebom_v2_catalog","status":"executed","sparql":"SELECT","results":[{"engineeringId":{"value":"A"}}]},0)
        self.assertEqual(r["semantic_verdict"],"PASS")
    def test_wrong_ids(self):
        r=evaluate(self.case,{"route":"ebom_v2_catalog","status":"executed","results":[{"engineeringId":{"value":"B"}}]},0)
        self.assertEqual(r["semantic_verdict"],"FAIL")
    def test_compile_only_is_not_evaluated(self):
        r=evaluate(self.case,{"route":"ebom_v2_catalog","status":"compiled","sparql":"SELECT"},0)
        self.assertEqual(r["semantic_verdict"],"NOT_EVALUATED")
    def test_empty_gold_is_valid(self):
        case=dict(self.case,expected_engineering_ids=[])
        r=evaluate(case,{"route":"ebom_v2_catalog","status":"executed","results":[]},0)
        self.assertEqual(r["semantic_verdict"],"PASS")
    def test_legacy_compiled_only(self):
        r=evaluate({"id":"x","question":"q"},{"method":"generic_v4_1_ontology_structural_validation","completed":True,"generated_sparql":"SELECT","graphdb_bindings":None},0)
        self.assertFalse(r["executed"])
        self.assertEqual(r["semantic_verdict"],"NOT_EVALUATED")
    def test_duplicate_ids_fail(self):
        r=evaluate(self.case,{"route":"ebom_v2_catalog","status":"executed","results":[{"engineeringId":{"value":"A"}},{"engineeringId":{"value":"A"}}]},0)
        self.assertEqual(r["semantic_verdict"],"FAIL")
if __name__=="__main__":unittest.main()
