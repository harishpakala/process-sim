from pathlib import Path
import pytest
from rdflib import URIRef
from rdflib import Graph, Namespace, RDF, Literal
from process_sim.selira.multi_contract_manager import MultiContractAutomationManager

ROOT = Path(__file__).resolve().parents[2]
A = Namespace("https://example.org/assetinventory/")
P = Namespace("https://example.org/productcatalog/")
D = Namespace("https://example.org/dexpi/")
E = Namespace("https://example.org/ecad/")
B = Namespace("https://example.org/engineeringbom/")
N = Namespace("urn:test:")


def fixture():
    manager = MultiContractAutomationManager.from_directory(ROOT / "archive/selira_integration/contracts")
    graph = Graph()
    for triple in [(N.asset, RDF.type, A.Asset), (N.asset, A.hasAssetIdentifier, Literal("a")),
                   (N.asset, A.hasProductIdentifier, Literal("p")),
                   (N.product, RDF.type, P.Product), (N.product, P.hasProductIdentifier, Literal("p")),
                   (N.equipment, RDF.type, D.InstrumentationFunction), (N.equipment, D.hasAssetIdentifier, URIRef("https://aas.example.com/FI101")),
                   (N.equipment, D.hasLocalId, Literal("FI_101")),
                   (N.device, RDF.type, E.Device), (N.device, E.hasAssetIdentifier, URIRef("https://aas.example.com/CV1006")),
                   (N.device, E.hasLocalId, Literal("CV-1006")),
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


def test_asset_identifier_change_is_isolated():
    m, g, flags = fixture()
    g.set((N.asset, A.hasAssetIdentifier, Literal("different")))
    r = m.submit(g, expected_version=0, **flags)
    assert r["verdict"] == "V"
    assert all(x["verdict"] == "V" for x in r["contracts"].values())


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
    g.set((N.equipment, D.hasLocalId, Literal("TI_105")))
    r = m.submit(g, expected_version=2, **flags, **reuse)
    assert r["verdict"] == "F" and r["reassessment"]["equivalent"]
    assert r["reassessment"]["selective_evaluations"] == 1
    r = m.submit(g, expected_version=2, **flags)
    assert r["reassessment"]["full_fallback"]
    assert r["reassessment"]["selective_evaluations"] == 4


@pytest.mark.parametrize("number,domain,node", [("02", D, N.equipment), ("03", E, N.device)])
def test_standalone_admission_and_reassessment(number, domain, node):
    root = ROOT / "archive/selira_integration/contracts"
    m = MultiContractAutomationManager([(root / "safsl" / f"SC-{number}.safsl",
                                         root / "bindings" / f"SC-{number}.json")])
    entry, _ = next(iter(m._contracts.values()))
    assert entry["requires_complete"] == [entry["focus_template_id"]]
    g = Graph()
    g.add((node, domain.hasLocalId, Literal("FI_101")))
    g.add((node, domain.hasAssetIdentifier, URIRef("https://aas.example.com/FI101")))
    flags = dict(evidence_complete=entry["requires_complete"], identity_normalized=True,
                 applicability_confirmed=True)
    reuse = dict(coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
    assert m.submit(g, expected_version=0)["verdict"] == "U"
    assert m.submit(Graph(), expected_version=0, **flags)["verdict"] == "NA"
    assert m.submit(g, expected_version=0, **flags)["committed"]
    g.set((node, domain.hasAssetIdentifier, URIRef("https://aas.example.com/TI1202")))
    r = m.submit(g, expected_version=1, **flags, **reuse)
    assert r["verdict"] == "F" and not r["committed"]
    outcome = next(iter(r["contracts"].values()))
    assert outcome["equivalent"] and outcome["violations"] == [str(node)]
    assert r["reassessment"]["equivalent"]
    assert r["reassessment"]["selective_evaluations"] == 1
    g.set((node, domain.hasAssetIdentifier, URIRef("https://aas.example.com/FI101")))
    g.remove((node, domain.hasLocalId, None))
    assert m.submit(g, expected_version=1, **flags)["verdict"] == "F"
    g.add((node, domain.hasLocalId, Literal("FI_101")))
    g.add((node, domain.hasLocalId, Literal("FI101")))
    assert m.submit(g, expected_version=1, **flags)["verdict"] == "F"
