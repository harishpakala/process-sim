import unittest
from ordered_semantics import compare_ordered

def score(actual, keys, limit=3, descending=False):
    ref={"head":{"vars":["entity","sort"]},"results":{"bindings":[{"entity":{"type":"uri","value":"urn:"+str(i)},"sort":{"type":"literal","value":k}} for i,k in enumerate(keys)]}}
    a={"head":{"vars":["x"]},"results":{"bindings":[{"x":{"type":"uri","value":"urn:"+str(i)}} for i in actual]}}
    return compare_ordered(a,ref,["entity"],{"entity":"x"},{"entity":"entity"},limit,descending)

class OrderedTests(unittest.TestCase):
    def test_boundary(self):
        self.assertTrue(score([0,1,3],["a","b","c","c"])["contract_match"])
    def test_internal(self):
        self.assertTrue(score([1,0,2],["a","a","b"])["contract_match"])
    def test_wrong_order(self):
        self.assertFalse(score([1,0,2],["a","b","c"])["contract_match"])
    def test_wrong_boundary(self):
        self.assertFalse(score([0,1,3],["a","b","c","d"])["contract_match"])
    def test_duplicate(self):
        self.assertFalse(score([0,0,2],["a","a","b"])["contract_match"])
    def test_short(self):
        self.assertFalse(score([0],["a","b"])["contract_match"])
    def test_descending(self):
        self.assertTrue(score([0,1,2],["c","b","a"],descending=True)["contract_match"])
if __name__=="__main__":
    unittest.main()
