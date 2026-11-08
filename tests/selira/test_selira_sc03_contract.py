import unittest
from process_sim.selira.sc03_contract import evaluate_sc03, assess_graphdb_sc03
from scripts.run_selira_sc03_experiment import synthetic_case


class SC03Tests(unittest.TestCase):
    def test_compatible_pressure_units(self):
        result = evaluate_sc03(synthetic_case())
        self.assertEqual(result["status"], "V")
        self.assertEqual(result["conversion"]["scale"], 100.0)
        self.assertFalse(result["authorization"])

    def test_incompatible_dimensions(self):
        self.assertEqual(evaluate_sc03(synthetic_case("degC"))["status"], "F")

    def test_missing_authenticated_evidence(self):
        case = synthetic_case()
        case["unitAssertions"][0]["authority"] = "UNVERIFIED"
        self.assertEqual(evaluate_sc03(case)["status"], "U")

    def test_unknown_unit_fails_closed(self):
        case = synthetic_case()
        case["unitAssertions"][1]["unit"] = "unspecified"
        self.assertEqual(evaluate_sc03(case)["status"], "U")

    def test_temperature_offset(self):
        case = synthetic_case()
        case["unitAssertions"][0]["unit"] = "degC"
        case["unitAssertions"][1]["unit"] = "K"
        result = evaluate_sc03(case)
        self.assertEqual(result["status"], "V")
        self.assertAlmostEqual(result["conversion"]["offset"], 273.15)

    def test_graphdb_bom_ea_is_not_measurement_unit(self):
        report = {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                  "truncated": False, "facts": [
                      {"s": "urn:bom", "p": "https://example.org/engineeringbom/hasUnit",
                       "o": "EA", "g": "urn:graph"}]}
        result = assess_graphdb_sc03(report)
        self.assertEqual(result["status"], "U")
        self.assertEqual(result["evidence"][0]["classification"],
                         "BOM_ITEM_COUNT_NOT_MEASUREMENT_UNIT")


if __name__ == "__main__":
    unittest.main()
