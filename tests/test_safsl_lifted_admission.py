import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, Literal, RDF, URIRef
from process_sim.safsl.shacl.compiler import SELIRA
from process_sim.safsl.shacl.lifted_sc01 import AI, PC
from process_sim.safsl.shacl.lifted_admission import admit_lifted_snapshot
from process_sim.safsl.shacl.sqlite_admission import SQLiteAdmissionStore

PROVENANCE = {
    "assetinventory": {"template_id": "https://example.org/sm/asset-inventory-template"},
    "productcatalog": {"template_id": "https://example.org/sm/product-catalog-template"},
}
REVISIONS = {"assetinventory": "test-asset-rev-1", "productcatalog": "test-product-rev-1"}


class LiftedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "admission.db")
        self.asset = URIRef("urn:asset:1")
        self.product = URIRef("urn:product:1")
        self.graph = Graph()
        self.graph.add((self.asset, RDF.type, SELIRA.SC01Asset))
        self.graph.add((self.asset, AI.hasProductReference, Literal("P-1")))
        self.graph.add((self.product, PC.hasAssetIdentifier, Literal("P-1")))

    def admit(self, **kwargs):
        return admit_lifted_snapshot(
            self.db, graph=self.graph, provenance=PROVENANCE,
            source_revisions=REVISIONS, **kwargs)

    def test_valid_snapshot_commits_locally(self):
        result = self.admit(evidence_complete=True, identity_normalized=True)
        self.assertEqual(result["verdict"], "V")
        self.assertTrue(result["committed"])
        graph, version, _ = SQLiteAdmissionStore(self.db).snapshot()
        self.assertEqual(version, 1)
        self.assertEqual(len(graph), len(self.graph))

    def test_missing_reference_rejected_without_commit(self):
        self.graph.remove((self.asset, AI.hasProductReference, None))
        result = self.admit(evidence_complete=True, identity_normalized=True)
        self.assertEqual(result["verdict"], "F")
        self.assertFalse(result["committed"])

    def test_unattested_snapshot_unknown(self):
        result = self.admit()
        self.assertEqual(result["verdict"], "U")
        self.assertFalse(result["committed"])


if __name__ == "__main__":
    unittest.main()
