#!/usr/bin/env python3
"""Focused, ontology-independent v4.1 compiler regression tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ontology_nl2sparql_generic_v4_1 import (substring_requested, normalize_output_names, validate, compile_plan)

ASSET="https://example.org/assetinventory/"
ECAD="https://example.org/ecad/"
CAT={
 "s0":{"domain":"assetinventory","properties":[
  {"predicate":ASSET+"hasAssetName","kind":"literal"},
  {"predicate":ASSET+"hasEquipmentTag","kind":"literal"}]},
 "s1":{"domain":"ecad","properties":[
  {"predicate":ECAD+"hasLocalId","kind":"literal"},
  {"predicate":ECAD+"hasAssetIdentifier","kind":"literal"}]}
}

class V41Regression(unittest.TestCase):
 def test_descriptive_plural_grounding(self):
  self.assertTrue(substring_requested(
   "List equipment tags and asset names from AssetInventory whose asset name contains temperature.",
   ASSET+"hasAssetName","temperature"))
 def test_identifier_grounding(self):
  self.assertTrue(substring_requested(
   "List ECAD asset identifiers and local IDs where the local ID contains TI.",
   ECAD+"hasLocalId","TI"))
 def test_unrequested_substring_rejected(self):
  self.assertFalse(substring_requested("List ECAD local IDs",ECAD+"hasLocalId","TI"))
 def test_wrong_predicate_rejected(self):
  self.assertFalse(substring_requested(
   "List asset names containing temperature",ASSET+"hasEquipmentTag","temperature"))
 def test_duplicate_invalid_names_normalized(self):
  plan={"fields":[
   {"name":"bad-name","shape":"s0","predicate":ASSET+"hasAssetName"},
   {"name":"bad-name","shape":"s0","predicate":ASSET+"hasEquipmentTag"},
   {"name":"bad-name","shape":"s0","predicate":ASSET+"hasAssetName"}],
   "filters":[],"unsupported":[]}
  normalize_output_names(plan)
  names=[f["name"] for f in plan["fields"]]
  self.assertEqual(names,["assetName","equipmentTag","assetName_2"])
  self.assertEqual(validate(plan,CAT,["assetinventory"],[],"Show asset names and equipment tags"),[])
  self.assertIn("SELECT DISTINCT ?assetName ?equipmentTag ?assetName_2",compile_plan(plan,{},[]))
 def test_b12_plan(self):
  question="List equipment tags and asset names from AssetInventory whose asset name contains temperature."
  plan={"fields":[{"name":"a","shape":"s0","predicate":ASSET+"hasEquipmentTag"},
                   {"name":"b","shape":"s0","predicate":ASSET+"hasAssetName"}],
        "filters":[{"shape":"s0","predicate":ASSET+"hasAssetName","contains":"temperature"}],
        "unsupported":[]}
  normalize_output_names(plan)
  self.assertEqual(validate(plan,CAT,["assetinventory"],[],question),[])
  self.assertIn("FILTER(CONTAINS(",compile_plan(plan,{},[]))
 def test_b13_plan(self):
  question="List ECAD asset identifiers and local IDs where the local ID contains TI."
  plan={"fields":[{"name":"a","shape":"s1","predicate":ECAD+"hasAssetIdentifier"},
                   {"name":"b","shape":"s1","predicate":ECAD+"hasLocalId"}],
        "filters":[{"shape":"s1","predicate":ECAD+"hasLocalId","contains":"TI"}],
        "unsupported":[]}
  normalize_output_names(plan)
  self.assertEqual(validate(plan,CAT,["ecad"],[],question),[])
  self.assertIn("FILTER(CONTAINS(",compile_plan(plan,{},[]))
 def test_unsupported_fails_closed(self):
  plan={"fields":[{"name":"a","shape":"s0","predicate":ASSET+"hasEquipmentTag"}],
        "filters":[],"unsupported":["maintenance cost"]}
  normalize_output_names(plan)
  self.assertTrue(any("Unsupported requirements:" in x for x in
   validate(plan,CAT,["assetinventory"],[],"List equipment tags and maintenance cost")))

if __name__=="__main__":unittest.main()
