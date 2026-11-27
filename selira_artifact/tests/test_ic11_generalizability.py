"""Synthetic configuration transfer, not industrial cross-domain validation."""
import base64
import json
import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, Literal

from selira.runtime.automation_manager import MultiContractAutomationManager

ROOT = Path(__file__).resolve().parents[1]
NS = Namespace("https://example.net/maintenance/")
TEMPLATE = str(NS.Template)


def configure(root, backend):
    for folder in ("registry", "contracts", "policies", "bindings"):
        shutil.copytree(ROOT / folder, root / folder)
    path = root / "registry/contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data["contracts"]:
        if entry["kind"] == "SC":
            entry["enabled"] = False
        else:
            entry["backend"] = backend
    encoded = base64.b64encode(TEMPLATE.encode()).decode()
    (root / "contracts/SC-05.safsl").write_text(
        'Specification Maintenance { Ref SubmodelTemplate items = "'
        + encoded + '"; Contract FieldConsistency { forall item in items { '
        'matches(item.Expected, item.Actual); } } }', encoding="utf-8")
    (root / "bindings/SC-05.json").write_text(json.dumps({
        "templates": {TEMPLATE: {"class": str(NS.Record),
            "target_by_predicate": True,
            "fields": {"Expected": str(NS.expected), "Actual": str(NS.actual)},
            "comparison_policy": {"kind": "lexical_equality"}}}
    }), encoding="utf-8")
    data["contracts"].append({
        "id": "SC-05", "kind": "SC", "enabled": True, "backend": "shacl",
        "specification": "contracts/SC-05.safsl", "binding": "bindings/SC-05.json"})
    (root / "policies/LP-05.safsl").write_text(
        """Specification SelectionAudit {
 StartTerminal=[Audit];
 Process Audit {
 Interface { Terminal Input START; Terminal Output DONE;
 Port Input Reassess; Port Input Reuse; Port Output Consistent; }
 Body { assign(Consistent, and(or(Reassess, Reuse), notS(and(Reassess, Reuse)))); }
 }
}""", encoding="utf-8")
    (root / "bindings/LP-05.json").write_text(json.dumps({
        "policy_id": "LP-05", "inputs": {"Reassess": "selection.reassess",
        "Reuse": "selection.reuse"}, "outputs": {"Consistent": "audit.consistent"}
    }), encoding="utf-8")
    data["contracts"].append({
        "id": "LP-05", "kind": "LP", "enabled": True, "backend": backend,
        "specification": "policies/LP-05.safsl", "binding": "bindings/LP-05.json",
        "activation": {"event": "ReassessmentSelectionCompleted",
                       "scope": "per_contract_instance"},
        "produces": "SelectionAuditCompleted"})
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("backend", ["ast", "sparql"])
def test_configuration_only_transfer(tmp_path, backend):
    configure(tmp_path, backend)
    manager = MultiContractAutomationManager.from_directory(tmp_path)
    assert len(manager._contracts) == 1
    context, trace = manager._policy_executor.dispatch(
        "DependencyProjectionCompleted", {
            "evidence.coverage_attested": True,
            "context.policy_unchanged": True,
            "context.authority_unchanged": True,
            "dependency.changed": False})
    assert context["audit.consistent"] is True
    assert trace[-1] == ("ReassessmentSelectionCompleted", "LP-05")
    graph = Graph()
    graph.add((NS.record, NS.expected, Literal("A")))
    graph.add((NS.record, NS.actual, Literal("A")))
    flags = dict(evidence_complete=[TEMPLATE], identity_normalized=True,
                 applicability_confirmed=True, coverage_attested=True,
                 policy_unchanged=True, authority_unchanged=True)
    assert manager.submit(graph, expected_version=0, **flags)["verdict"] == "V"
    graph.add((NS.other, NS.note, Literal("unrelated")))
    result = manager.submit(graph, expected_version=1, **flags)
    assert result["verdict"] == "V"
    assert result["reassessment"]["selective_evaluations"] == 0
    graph.set((NS.record, NS.actual, Literal("B")))
    result = manager.submit(graph, expected_version=2, **flags)
    assert result["verdict"] == "F"
    assert result["reassessment"]["selective_evaluations"] == 1
    assert result["reassessment"]["equivalent"]
    assert manager.submit(graph, expected_version=2)["verdict"] == "U"
    graph.set((NS.record, NS.actual, Literal("A")))
    result = manager.submit(graph, expected_version=2,
                            **dict(flags, coverage_attested=False))
    assert result["verdict"] == "V"
    assert result["reassessment"]["full_fallback"]
    assert result["reassessment"]["selective_evaluations"] == 1


def test_invalid_extension_binding(tmp_path):
    configure(tmp_path, "ast")
    path = tmp_path / "bindings/LP-05.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["inputs"]["Unknown"] = "unknown"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        MultiContractAutomationManager.from_directory(tmp_path)
