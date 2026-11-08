"""Created: 2026-10-31
Author: Harish"""

import base64
import tempfile
import unittest
from pathlib import Path

from rdflib import Namespace, RDF

from process_sim.safsl.shacl.compiler import compile_contract
from process_sim.safsl.shacl.sqlite_admission import SQLiteAdmissionStore

EX = Namespace("https://example.org/selira/")
A, P = "urn:example:aas:template:AssetInventory", "urn:example:aas:template:ProductCatalog"
enc = lambda s: base64.b64encode(s.encode()).decode()
SOURCE = f"""Specification Integrity {{
 Ref SubmodelTemplate assets = "{enc(A)}";
 Ref SubmodelTemplate products = "{enc(P)}";
 Contract SC_01 {{
  forall asset in assets {{
   existsExactlyOne product in products where matches(asset.productRef, product.canonicalId);
  }}
 }}
}}"""
BINDINGS = {"templates": {
 A: {"class": str(EX.Asset), "fields": {"productRef": str(EX.productRef)}},
 P: {"class": str(EX.CanonicalProduct), "fields": {"canonicalId": str(EX.canonicalId)}},
}}
TTL, MANIFEST = compile_contract(SOURCE, BINDINGS)
TRIPLES = [
    (EX.asset, RDF.type, EX.Asset),
    (EX.asset, EX.productRef, EX.P1),
    (EX.product, RDF.type, EX.CanonicalProduct),
    (EX.product, EX.canonicalId, EX.P1),
]


class TestSQLiteAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "admission.sqlite"
        self.store = SQLiteAdmissionStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def attempt(self, **overrides):
        args = dict(shapes_ttl=TTL, manifest=MANIFEST,
                    changed_template_ids=[A, P],
                    source_revisions={A: "r1", P: "r1"},
                    expected_version=0, additions=TRIPLES,
                    evidence_complete=[A, P], identity_normalized=True)
        args.update(overrides)
        return self.store.admit(**args)

    def test_persistent_commit_and_audit(self):
        result = self.attempt()
        self.assertEqual((result["verdict"], result["committed"]), ("V", True))
        graph, version, revisions = SQLiteAdmissionStore(self.path).snapshot()
        self.assertEqual(version, 1)
        self.assertEqual(len(graph), 4)
        self.assertEqual(revisions[A], "r1")

    def test_stale_write_not_committed(self):
        self.attempt()
        result = self.attempt()
        self.assertEqual((result["verdict"], result["committed"]), ("U", False))
        self.assertEqual(self.store.snapshot()[1], 1)

    def test_invalid_graph_does_not_commit(self):
        result = self.attempt(additions=TRIPLES[:2])
        self.assertEqual((result["verdict"], result["committed"]), ("F", False))
        self.assertEqual(self.store.snapshot()[1], 0)

    def test_missing_completeness_is_unknown(self):
        result = self.attempt(evidence_complete=[A])
        self.assertEqual((result["verdict"], result["committed"]), ("U", False))


if __name__ == "__main__":
    unittest.main()
