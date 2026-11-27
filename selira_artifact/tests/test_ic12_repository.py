from pathlib import Path

from rdflib import Graph, URIRef
from selira.runtime.admission import VersionedGraphStore
from selira.runtime.automation_manager import MultiContractAutomationManager

ROOT = Path(__file__).resolve().parents[1]


def test_ic12_repository_default():
    manager = MultiContractAutomationManager.from_directory(ROOT)
    assert isinstance(manager.store, VersionedGraphStore)


def test_ic12_repository_injected():
    store = VersionedGraphStore()
    manager = MultiContractAutomationManager.from_directory(ROOT, store=store)
    assert manager.store is store
    result = manager.submit(Graph(), expected_version=1)
    assert result["verdict"] == "U"
    assert not result["committed"]
    assert store.snapshot()[1] == 0


def test_ic12_repository_snapshot_and_compare():
    store = VersionedGraphStore()
    graph = Graph()
    triple = tuple(URIRef("urn:" + x) for x in ("s", "p", "o"))
    graph.add(triple)
    assert store.compare_and_commit(0, graph) == (True, 1)
    graph.remove(triple)
    assert store.compare_and_commit(0, graph) == (False, 1)
    snapshot, version = store.snapshot()
    assert version == 1 and triple in snapshot
    snapshot.remove(triple)
    assert triple in store.snapshot()[0]


def test_ic12_repository_direct_constructor():
    store = VersionedGraphStore()
    manager = MultiContractAutomationManager(
        [(ROOT / "contracts/SC-01.safsl", ROOT / "bindings/SC-01.json")],
        store=store)
    assert manager.store is store
