from pathlib import Path
from rdflib import Graph, URIRef, Literal, RDF
from selira.runtime.selective_manager import SelectiveAutomationManager

ROOT = Path(__file__).resolve().parents[1]

def test_selective_cache_lifecycle():
    paths = [(ROOT/"contracts"/"SC-01.safsl", ROOT/"bindings"/"SC-01.json")]
    m = SelectiveAutomationManager(paths)
    entry,_ = next(iter(m._contracts.values()))
    fp,tp,tc = (URIRef(entry[k]) for k in ("focus_predicate","catalog_predicate","catalog_class"))
    a,b,t = map(URIRef, ("urn:test:a","urn:test:b","urn:test:t"))
    g = Graph()
    g.add((a,fp,Literal("x")))
    g.add((t,RDF.type,tc))
    g.add((t,tp,Literal("x")))
    def submit(graph, **flags):
        opts = dict(expected_version=m.store.snapshot()[1], evidence_complete=entry["requires_complete"],
                    identity_normalized=True, applicability_confirmed=True, coverage_attested=True,
                    policy_unchanged=True, authority_unchanged=True)
        opts.update(flags)
        return m.submit(graph, **opts)
    assert submit(g)["executed_instances"] == 1
    assert submit(g)["reused_instances"] == 1
    bad = Graph()+g
    bad.set((a,fp,Literal("missing")))
    assert submit(bad)["verdict"] == "F"
    assert submit(g)["executed_instances"] == 0
    expanded = Graph()+g
    expanded.add((b,fp,Literal("x")))
    assert submit(expanded)["executed_instances"] == 1
    assert submit(g)["executed_instances"] == 0
    assert submit(g,evidence_complete=())["verdict"] == "U"
    assert submit(g,coverage_attested=False)["executed_instances"] == 1
    m._cache = None
    assert submit(g)["executed_instances"] == 1
    assert submit(g,expected_version=-1)["verdict"] == "U"
    full = SelectiveAutomationManager(paths,strategy="full")
    opts = dict(expected_version=0,evidence_complete=entry["requires_complete"],identity_normalized=True,applicability_confirmed=True)
    assert full.submit(g,**opts)["executed_instances"] == 1
    opts["expected_version"] = 1
    assert full.submit(g,**opts)["executed_instances"] == 1
