"""Phase 4 router offline regression."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
import dtwise_phase4_router as router
Q="Which ECAD devices are functionally associated with condenser C-001?"
class RouterTests(unittest.TestCase):
    def test_route_ebom(self):self.assertEqual(router.route(Q),"ebom_v2_catalog")
    def test_route_legacy(self):self.assertEqual(router.route("List asset inventory records"),"generic_v4_1")
    def test_compile(self):
        result=router.handle_ebom(Q,"",False)
        self.assertEqual(result["status"],"compiled")
        self.assertEqual(len(result["path"]),3)
    def test_reject_physical(self):
        with self.assertRaises(ValueError):
            router.handle_ebom("Which ECAD devices are physically installed and functionally associated with condenser C-001?","",False)
    def test_no_fallback(self):
        self.assertEqual(router.route("Which OPC devices are functionally associated with condenser C-001?"),"ebom_v2_catalog")
    def test_legacy_options(self):
        with patch.object(router.subprocess,"call",return_value=0) as mock:
            self.assertEqual(router.main(["--question","List asset inventory records","--skip-execution","--model","test-model"]),0)
        command=mock.call_args.args[0]
        self.assertIn("--skip-execution",command)
        self.assertIn("test-model",command)
    def test_reject_projection(self):
        with patch.object(router,"handle_ebom") as mock:
            self.assertEqual(router.main(["--question",Q+" Return serial numbers.","--skip-execution"]),2)
            mock.assert_not_called()
if __name__=="__main__":unittest.main()
