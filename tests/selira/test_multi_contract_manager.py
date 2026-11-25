from pathlib import Path
from rdflib import Graph, Namespace, RDF, Literal
from process_sim.selira.multi_contract_manager import MultiContractAutomationManager

ROOT = Path(__file__).resolve().parents[2]
A = Namespace("https://example.org/assetinventory/")
P = Namespace("https://example.org/productcatalog/")
D = Namespace("https://example.org/dexpi/")
O = Namespace("https://example.org/opcuaconnectivity/")
B = Namespace("https://example.org/engineeringbom/")
N = Namespace("urn:test:")


def fixture():
    manager = MultiContractAutomationManager.from_directory(ROOT / "selira_integration/contracts")
    graph = Graph()
    for triple in [(N.asset, RDF.type, A.Asset), (N.asset, A.hasAssetIdentifier, Literal("a")),
                   (N.asset, A.hasProductIdentifier, Literal("p")),
                   (N.product, RDF.type, P.Product), (N.product, P.hasProductIdentifier, Literal("p")),
                   (N.equipment, RDF.type, D.Equipment), (N.equipment, D.hasAssetIdentifier, Literal("a")),
                   (N.signal, RDF.type, O.SignalMapping), (N.signal, O.hasAssetIdentifier, Literal("a")),
                   (N.bom, RDF.type, B.BOMItemRecord), (N.bom, B.hasProductIdentifier, Literal("p"))]:
        graph.add(triple)
    evidence = {t for c, _ in manager._contracts.values() for t in c["requires_complete"]}
    return manager, graph, dict(evidence_complete=evidence, identity_normalized=True,
                                applicability_confirmed=True)


def test_atomic_multi_contract_admission():
    m, g, flags = fixture()
    first = m.submit(g, expected_version=0, **flags)
    assert first["committed"] and first["verdict"] == "V"
    assert len(first["contracts"]) == 4
    g.remove((N.product, P.hasProductIdentifier, None))
    # Missing target identifier is unresolved under the restricted projection.
    assert m.submit(g, expected_version=1, **flags)["verdict"] == "U"
    g.remove((N.product, RDF.type, P.Product))
    rejected = m.submit(g, expected_version=1, **flags)
    assert rejected["verdict"] == "F" and not rejected["committed"]
    assert {r["id"] for r in rejected["contracts"].values() if r["verdict"] == "F"} == {"SC_01", "SC_04"}
    snapshot, version = m.store.snapshot()
    assert version == 1 and (N.product, P.hasProductIdentifier, Literal("p")) in snapshot


def test_asset_change_affects_two_contracts():
    m, g, flags = fixture()
    g.set((N.asset, A.hasAssetIdentifier, Literal("different")))
    r = m.submit(g, expected_version=0, **flags)
    assert r["verdict"] == "F"
    assert {x["id"] for x in r["contracts"].values() if x["verdict"] == "F"} == {"SC_02", "SC_03"}


def test_missing_attestation_and_stale_version():
    m, g, flags = fixture()
    assert m.submit(g, expected_version=0)["verdict"] == "U"
    assert m.submit(g, expected_version=1, **flags)["verdict"] == "U"
    assert m.store.snapshot()[1] == 0


def test_empty_scope():
    m, _, flags = fixture()
    assert m.submit(Graph(), expected_version=0, **flags)["verdict"] == "NA"


def test_selective_shared_dependencies():
    m, g, flags = fixture()
    assert m.submit(g, expected_version=0, **flags)["committed"]
    reuse = dict(coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
    g.add((N.unreferenced, RDF.type, P.Product))
    g.add((N.unreferenced, P.hasProductIdentifier, Literal("unused")))
    r = m.submit(g, expected_version=1, **flags, **reuse)
    assert r["committed"] and r["reassessment"]["selective_evaluations"] == 0
    assert r["reassessment"]["full_evaluations"] == 4
    g.set((N.product, P.hasProductIdentifier, Literal("other")))
    r = m.submit(g, expected_version=2, **flags, **reuse)
    assert r["verdict"] == "F" and r["reassessment"]["equivalent"]
    assert r["reassessment"]["selective_evaluations"] == 2
    g.set((N.product, P.hasProductIdentifier, Literal("p")))
    g.set((N.asset, A.hasAssetIdentifier, Literal("other")))
    r = m.submit(g, expected_version=2, **flags, **reuse)
    assert r["verdict"] == "F" and r["reassessment"]["equivalent"]
    assert r["reassessment"]["selective_evaluations"] == 2
    r = m.submit(g, expected_version=2, **flags)
    assert r["reassessment"]["full_fallback"]
    assert r["reassessment"]["selective_evaluations"] == 4
