import unittest
from request_guard import preflight

class RequestGuardTests(unittest.TestCase):
    def test_write_forms(self):
        for q in ["Delete all ECAD Devices with DeviceType Pressure.","Remove ECAD Devices whose DeviceType is Pressure.","Erase every ECAD Device with DeviceType Pressure.","Perform a deletion of ECAD Devices of DeviceType Pressure.","Delete the ECAD Device records where DeviceType equals Pressure.","Please update the asset.","INSERT a record"]:
            with self.subTest(q=q):
                self.assertEqual(preflight(q),{"decision":"reject","reason":"write_operation"})
    def test_retrieval_forms(self):
        for verb in ["Show","List","Retrieve","Return","Display"]:
            self.assertEqual(preflight(verb+" ECAD Devices.")["decision"],"continue")
    def test_property_value(self):
        self.assertEqual(preflight("Show Devices with LocalId Delete.")["decision"],"continue")
    def test_empty(self):
        self.assertEqual(preflight(" ")["decision"],"clarify")
    def test_unrecognized_not_approved(self):
        self.assertEqual(preflight("Could you delete an asset?")["decision"],"continue")

if __name__=="__main__":
    unittest.main()
