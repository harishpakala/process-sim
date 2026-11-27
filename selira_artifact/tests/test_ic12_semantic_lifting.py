import json
from pathlib import Path
from copy import deepcopy

import pytest
from rdflib.compare import isomorphic

pytest.importorskip("aas_core3_1")
pytest.importorskip("semantic.template_lifting")
from aas_core3_1.jsonization import submodel_from_jsonable
from semantic.config import TARGETS
from semantic.template_lifting import build_template_graph
from semantic.instance_lifting import build_instance_graph
from selira.runtime.semantic_lifting import SemanticLiftingAdapter


def documents(domain):
    _, template, instance = next(t for t in TARGETS if t[0] == domain)
    return (json.loads(template.read_text(encoding="utf-8")),
            json.loads(instance.read_text(encoding="utf-8")))


@pytest.mark.parametrize("domain", ["assetinventory", "productcatalog"])
def test_ic12_lifting_equivalence(domain, monkeypatch):
    import semantic.template_lifting as tl
    import semantic.instance_lifting as il

    def forbidden(*args, **kwargs):
        pytest.fail("Lifting adapter must not publish to GraphDB")

    monkeypatch.setattr(tl, "push_graph_to_graphdb", forbidden)
    monkeypatch.setattr(il, "push_graph_to_graphdb", forbidden)
    template, instance = documents(domain)
    before = deepcopy((template, instance))
    adapter = SemanticLiftingAdapter(domain, template)
    assert isomorphic(adapter.template_graph(),
                      build_template_graph(submodel_from_jsonable(template), domain))
    assert isomorphic(adapter.lift_instance(instance),
                      build_instance_graph(submodel_from_jsonable(instance),
                                           domain, template["id"]))
    assert (template, instance) == before
    graph = adapter.template_graph()
    graph.remove((None, None, None))
    assert len(adapter.template_graph()) > 0


def test_ic12_lifting_rejects_unsupported():
    template, instance = documents("assetinventory")
    adapter = SemanticLiftingAdapter("assetinventory", template)
    instance["submodelElements"].append(
        {"modelType": "File", "idShort": "Unsupported", "contentType": "text/plain"})
    with pytest.raises(ValueError, match="Unsupported lifting element"):
        adapter.lift_instance(instance)


def test_ic12_lifting_rejects_duplicate_paths():
    template, instance = documents("assetinventory")
    adapter = SemanticLiftingAdapter("assetinventory", template)
    instance["submodelElements"].append(deepcopy(instance["submodelElements"][0]))
    with pytest.raises(ValueError, match="duplicate sibling"):
        adapter.lift_instance(instance)


def test_ic12_lifting_rejects_template_as_instance():
    template, _ = documents("assetinventory")
    adapter = SemanticLiftingAdapter("assetinventory", template)
    with pytest.raises(ValueError, match="identifiers must differ"):
        adapter.lift_instance(template)
