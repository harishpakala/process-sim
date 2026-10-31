import base64
import unittest
from rdflib import Graph, Namespace, RDF
from process_sim.safsl.shacl.compiler import compile_contract
from process_sim.safsl.shacl.admission import (
    VersionedGraphStore, Verdict, admit, affected_contracts
)

EX = Namespace("https://example.org/selira/")
A = "urn:example:aas:template:AssetInventory"
P = "urn:example:aas:template:ProductCatalog"
b64 = lambda s: base64.b64encode(s.encode()).decode()
SOURCE = f"""Specification Integrity {{
 Ref SubmodelTemplate assets = "{b64(A)}";
 Ref SubmodelTemplate products = "{b64(P)}";
 Contract SC_01 {{
  forall asset in assets {{
   existsExactlyOne product in products
    where matches(asset.productRef, product.canonicalId);
  }}
 }}
}}"""
BINDINGS = {"templates": {
 A: {"class": str(EX.Asset), "fields": {"productRef": str(EX.productRef)}},
 P: {"class": str(EX.CanonicalProduct), "fields": {"canonicalId": str(EX.canonicalId)}}
}}
TTL, MANIFEST = compile_contract(SOURCE, BINDINGS)


def base_graph():
    g = Graph()
    g.add((EX.a, RDF.type, EX.Asset))
    g.add((EX.a, EX.productRef, EX.P1))
    g.add((EX.p1, RDF.type, EX.CanonicalProduct))
    g.add((EX.p1, EX.canonicalId, EX.P1))
    return g


def check(store, changed=(A,), **kwargs):
    return admit(store, shapes_ttl=TTL, manifest=MANIFEST,
                 changed_template_ids=changed, evidence_complete={A, P},
                 identity_normalized=True, **kwargs)


class TestAdmission(unittest.TestCase):
    def test_valid_commit(self):
        store = VersionedGraphStore(base_graph())
        d = check(store)
        self.assertEqual((d.verdict, d.committed, d.version), (Verdict.V, True, 1))

    def test_zero_match_rejected(self):
        store = VersionedGraphStore(base_graph())
        d = check(store, removals=[(EX.p1, EX.canonicalId, EX.P1)])
        self.assertEqual(d.verdict, Verdict.F)
        self.assertFalse(d.committed)
        self.assertEqual(store.snapshot()[1], 0)

    def test_catalog_duplicate_rejected(self):
        store = VersionedGraphStore(base_graph())
        d = check(store, changed=(P,), additions=[
            (EX.p2, RDF.type, EX.CanonicalProduct),
            (EX.p2, EX.canonicalId, EX.P1)])
        self.assertEqual(d.verdict, Verdict.F)

    def test_incomplete_is_unknown(self):
        store = VersionedGraphStore(base_graph())
        d = admit(store, shapes_ttl=TTL, manifest=MANIFEST,
                  changed_template_ids=[P], evidence_complete=[A],
                  identity_normalized=True)
        self.assertEqual(d.verdict, Verdict.U)

    def test_empty_focus_is_na(self):
        store = VersionedGraphStore()
        self.assertEqual(check(store).verdict, Verdict.NA)

    def test_stale_version_fails_closed(self):
        store = VersionedGraphStore(base_graph())
        self.assertEqual(check(store, expected_version=5).verdict, Verdict.U)

    def test_identity_not_confirmed(self):
        store = VersionedGraphStore(base_graph())
        d = admit(store, shapes_ttl=TTL, manifest=MANIFEST,
                  changed_template_ids=[A], evidence_complete=[A, P])
        self.assertEqual(d.verdict, Verdict.U)

    def test_both_dependencies_trigger(self):
        self.assertEqual(len(affected_contracts(MANIFEST, [A])), 1)
        self.assertEqual(len(affected_contracts(MANIFEST, [P])), 1)


if __name__ == "__main__":
    unittest.main()
