"""Synthetic schema transfer test; not an industrial case study."""
import base64
import json
import shutil
from pathlib import Path

from rdflib import Graph, Namespace, Literal, RDF
from process_sim.selira.multi_contract_manager import MultiContractAutomationManager


def test_configuration_only_lifecycle(tmp_path):
    ns = Namespace("https://example.net/independent-model/")
    template = str(ns.Template)
    encoded = base64.b64encode(template.encode()).decode()
    root = tmp_path / "contracts"
    (root / "safsl").mkdir(parents=True)
    (root / "bindings").mkdir()
    (root / "safsl/FieldConsistency.safsl").write_text(
        'Specification IndependentModel { Ref SubmodelTemplate items = "'
        + encoded + '"; Contract FieldConsistency { forall item in items { '
        'matches(item.Expected, item.Actual); } } }', encoding="utf-8")
    (root / "bindings/FieldConsistency.json").write_text(json.dumps({
        "templates": {template: {"class": str(ns.Record),
            "target_by_predicate": True,
            "fields": {"Expected": str(ns.expected), "Actual": str(ns.actual)},
            "comparison_policy": {"kind": "lexical_equality"}}}
    }), encoding="utf-8")
    policies = tmp_path / "independent-policies"
    policies.mkdir()
    original = Path(__file__).resolve().parents[2] / "selira_integration/contracts/safsl"
    paths = []
    for name in ("LP-03", "LP-04"):
        path = policies / (name + ".safsl")
        shutil.copyfile(original / (name + ".safsl"), path)
        paths.append(path)
    manager = MultiContractAutomationManager.from_directory(root, policy_paths=paths)

    def graph(actual="Type-A", unrelated=False):
        g = Graph()
        g.add((ns.record, RDF.type, ns.Record))
        g.add((ns.record, ns.expected, Literal("Type-A")))
        g.add((ns.record, ns.actual, Literal(actual)))
        if unrelated:
            g.add((ns.other, ns.note, Literal("unrelated")))
        return g

    def submit(g, version, evidence=True, coverage=True):
        return manager.submit(g, expected_version=version,
            evidence_complete=[template] if evidence else [],
            identity_normalized=True, applicability_confirmed=True,
            coverage_attested=coverage, policy_unchanged=True,
            authority_unchanged=True)

    first = submit(graph(), 0)
    assert first["verdict"] == "V" and first["committed"] and first["version"] == 1
    unrelated = submit(graph(unrelated=True), 1)
    assert unrelated["verdict"] == "V" and unrelated["version"] == 2
    assert unrelated["reassessment"]["equivalent"]
    assert unrelated["reassessment"]["selective_evaluations"] == 0
    rejected = submit(graph("Type-B"), 2)
    assert rejected["verdict"] == "F" and not rejected["committed"]
    assert rejected["version"] == 2
    assert rejected["reassessment"]["equivalent"]
    assert rejected["reassessment"]["selective_evaluations"] == 1
    deferred = submit(graph(), 2, evidence=False)
    assert deferred["verdict"] == "U" and not deferred["committed"]
    assert deferred["version"] == 2
    fallback = submit(graph(), 2, coverage=False)
    assert fallback["verdict"] == "V" and fallback["version"] == 3
    assert fallback["reassessment"]["full_fallback"]
    assert fallback["reassessment"]["equivalent"]
    assert fallback["reassessment"]["selective_evaluations"] == 1
