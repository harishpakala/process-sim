import unittest
from result_semantics import compare

def result(values, var="x", kind="uri"):
    return {"head":{"vars":[var]},"results":{"bindings":[{var:{"type":kind,"value":v}} for v in values]}}

class ContractTests(unittest.TestCase):
    def score(self,a,e,mode="set"):
        return compare(a,e,{"mode":mode,"roles":["Device"]},{"Device":"x"},{"Device":"y"})
    def test_overlapping_or(self):
        a=result(["urn:a","urn:b","urn:c"])
        e=result(["urn:a","urn:b","urn:c","urn:a"],"y")
        self.assertTrue(self.score(a,e)["contract_match"])
        self.assertFalse(self.score(a,e)["bag_match"])
    def test_disjoint_or(self):
        self.assertTrue(self.score(result(["urn:a","urn:b"]),result(["urn:b","urn:a"],"y"))["contract_match"])
    def test_missing_entity(self):
        self.assertFalse(self.score(result(["urn:a"]),result(["urn:a","urn:b"],"y"))["contract_match"])
    def test_bag_multiplicity(self):
        self.assertFalse(self.score(result(["Pressure"],kind="literal"),result(["Pressure","Pressure"],"y","literal"),"bag")["contract_match"])
    def test_rdf_type(self):
        self.assertFalse(self.score(result(["urn:a"]),result(["urn:a"],"y","literal"))["contract_match"])
    def test_pending_order(self):
        with self.assertRaises(ValueError):
            self.score(result([]),result([],"y"),"ordered_pending")
    def test_empty_requires_review(self):
        self.assertTrue(self.score(result([]),result([],"y"))["structural_review_required"])

if __name__=="__main__":
    unittest.main()
