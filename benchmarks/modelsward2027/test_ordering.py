import unittest
from inspect_ordering import inspect

def rows(*values):
    return [{"sort":{"type":"literal","value":v}} for v in values]

class OrderingTests(unittest.TestCase):
    def test_boundary_tie(self):
        self.assertTrue(inspect(rows("a","b","b","c"),2)["boundary_tie"])
    def test_internal_tie(self):
        r=inspect(rows("a","a","b","c"),3)
        self.assertFalse(r["boundary_tie"])
        self.assertEqual(r["repeated_key_groups"],1)
    def test_short_result(self):
        self.assertFalse(inspect(rows("a"),5)["boundary_tie"])
    def test_missing_key(self):
        with self.assertRaises(ValueError):
            inspect([{}],1)

if __name__=="__main__":
    unittest.main()
