"""Full-validation multi-contract coordinator for local RDF snapshots.

Uses existing SAFSL compilation and versioned store. No incremental SHACL,
remote transactions, or independent authentication of caller attestations.
"""
import json
from pathlib import Path
from threading import RLock

from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH
from pyshacl import validate
from .reassessment.multi_contract import compare
from process_sim.safsl.shacl.compiler import compile_contract
from process_sim.safsl.shacl.identifier_comparison import identifier_matches
from process_sim.safsl.shacl.admission import VersionedGraphStore, Verdict


class MultiContractAutomationManager:
    def __init__(self, artifacts, *, policy_paths=None):
        self._policy_paths = tuple(map(Path, policy_paths)) if policy_paths is not None else None
        if self._policy_paths is not None and len(self._policy_paths) != 2:
            raise ValueError("Expected impact and selection policy paths")
        self._contracts = {}
        self.store = VersionedGraphStore()
        self._lock = RLock()
        self.history = []
        for source_path, binding_path in artifacts:
            bindings = json.loads(Path(binding_path).read_text(encoding="utf-8"))
            ttl, manifest = compile_contract(Path(source_path).read_text(encoding="utf-8"), bindings)
            entry, = manifest["contracts"]
            key = entry["shape"]
            if key in self._contracts:
                raise ValueError("Duplicate contract shape")
            shapes = Graph().parse(data=ttl, format="turtle")
            shape = URIRef(key)
            fp = URIRef(entry["focus_predicate"])
            if (shape, SH.targetSubjectsOf, fp) not in shapes:
                raise ValueError("Only predicate-targeted integrity contracts supported")
            if entry.get("kind") == "standalone_match":
                if entry["requires_complete"] != [entry["focus_template_id"]]:
                    raise ValueError("Standalone matches require one complete Submodel")
            else:
                target = bindings["templates"][entry["catalog_template_id"]]
                if not target.get("lexical_match") or target.get("match_by_predicate"):
                    raise ValueError("Only lexical, class-targeted lookup supported")
            self._contracts[key] = (entry, ttl)
        if not self._contracts:
            raise ValueError("At least one contract required")

    @classmethod
    def from_directory(cls, directory, *, policy_paths=None):
        directory = Path(directory)
        return cls([(p, directory / "bindings" / (p.stem + ".json"))
                    for p in sorted((directory / "safsl").glob("*.safsl"))
                    if (directory / "bindings" / (p.stem + ".json")).is_file()],
                   policy_paths=policy_paths)

    def _evaluate(self, graph, entry, ttl, evidence, identity, applicability):
        fp = URIRef(entry["focus_predicate"])
        if entry.get("kind") == "standalone_match":
            return self._evaluate_standalone(graph, entry, ttl, evidence,
                                             identity, applicability)
        tp = URIRef(entry["catalog_predicate"])
        tc = URIRef(entry["catalog_class"])
        focus = set(graph.subjects(fp, None))
        targets = set(graph.subjects(RDF.type, tc))
        result = {"id": entry["id"], "focus_count": len(focus),
                  "target_count": len(targets), "violations": [], "equivalent": None}
        def finish(verdict, reason):
            return dict(result, verdict=verdict.value, reason=reason)
        if not identity or not applicability or not set(entry["requires_complete"]) <= evidence:
            return finish(Verdict.U, "Required snapshot attestations missing")
        index = {}
        for nodes, predicate in ((focus, fp), (targets, tp)):
            for node in nodes:
                values = set(graph.objects(node, predicate))
                if len(values) != 1 or not str(next(iter(values), "")).strip():
                    return finish(Verdict.U, "Projection requires one nonempty identifier term")
                if predicate == tp:
                    index.setdefault(str(next(iter(values))), set()).add(node)
        if not focus:
            return finish(Verdict.NA, "Confirmed empty predicate-selected population")
        expected = {str(n) for n in focus
                    if len(index.get(str(next(graph.objects(n, fp))), set())) != 1}
        conforms, report, _ = validate(graph, shacl_graph=Graph().parse(data=ttl, format="turtle"),
                                       inference="none", advanced=False, abort_on_first=False)
        actual = {str(n) for n in report.objects(None, SH.focusNode)}
        result["violations"] = sorted(actual)
        result["equivalent"] = actual == expected and bool(conforms) == (not expected)
        if not result["equivalent"]:
            return finish(Verdict.U, "Reference and SHACL disagreement")
        return finish(Verdict.V if conforms else Verdict.F,
                      "Integrity satisfied" if conforms else "Integrity violated")

    def _evaluate_standalone(self, graph, entry, ttl, evidence, identity, applicability):
        focus = set(graph.subjects(URIRef(entry["focus_predicate"]), None))
        result = {"id": entry["id"], "focus_count": len(focus),
                  "target_count": 0, "violations": [], "equivalent": None}

        def finish(verdict, reason):
            return dict(result, verdict=verdict.value, reason=reason)

        if not identity or not applicability or not set(entry["requires_complete"]) <= evidence:
            return finish(Verdict.U, "Required snapshot attestations missing")
        if not focus:
            return finish(Verdict.NA, "Confirmed empty predicate-selected population")
        policy = entry["comparison_policy"]
        if policy["kind"] != "normalized_asset_identifier":
            return finish(Verdict.U, "Unsupported identifier comparison policy")
        exceptions = tuple(tuple(pair) for pair in policy.get("exceptions", []))
        left = URIRef(entry["left_predicate"])
        right = URIRef(entry["right_predicate"])
        expected = set()
        for node in focus:
            local = set(graph.objects(node, left))
            asset = set(graph.objects(node, right))
            valid = False
            if len(local) == len(asset) == 1:
                try:
                    valid = identifier_matches(str(next(iter(local))),
                                               str(next(iter(asset))),
                                               exceptions=exceptions)
                except ValueError:
                    pass
            if not valid:
                expected.add(str(node))
        conforms, report, _ = validate(graph, shacl_graph=Graph().parse(data=ttl, format="turtle"),
                                       inference="none", advanced=False, abort_on_first=False)
        actual = {str(n) for n in report.objects(None, SH.focusNode)}
        result["violations"] = sorted(actual)
        result["equivalent"] = actual == expected and bool(conforms) == (not expected)
        if not result["equivalent"]:
            return finish(Verdict.U, "Reference and SHACL disagreement")
        return finish(Verdict.V if conforms else Verdict.F,
                      "Integrity satisfied" if conforms else "Integrity violated")

    def submit(self, candidate, *, expected_version, evidence_complete=(),
               identity_normalized=False, applicability_confirmed=False,
               coverage_attested=False, policy_unchanged=False, authority_unchanged=False):
        with self._lock:
            current, version = self.store.snapshot()
            reassessment = None
            proposed = Graph()
            proposed += candidate
            outcomes = {}
            committed = False
            new_version = version
            if version != expected_version:
                verdict, reason = Verdict.U, "Stale snapshot version"
            else:
                evidence = set(evidence_complete)
                for key, (entry, ttl) in self._contracts.items():
                    try:
                        outcomes[key] = self._evaluate(proposed, entry, ttl, evidence,
                                                       identity_normalized, applicability_confirmed)
                    except Exception as exc:
                        outcomes[key] = {"id": entry["id"], "verdict": "U",
                                         "reason": f"Validation error: {exc}"}
                values = {r["verdict"] for r in outcomes.values()}
                if version > 0 and "U" not in values:
                    try:
                        reassessment = compare(current, proposed, self._contracts,
                                               coverage_attested=coverage_attested,
                                               policy_unchanged=policy_unchanged,
                                               authority_unchanged=authority_unchanged,
                                               policy_paths=self._policy_paths)
                        if not reassessment["equivalent"]:
                            values.add("U")
                    except Exception:
                        values.add("U")
                if "F" in values:
                    verdict, reason = Verdict.F, "At least one contract violated"
                elif "U" in values:
                    verdict, reason = Verdict.U, "At least one contract unresolved"
                elif values == {"NA"}:
                    verdict, reason = Verdict.NA, "All contract populations empty"
                else:
                    committed, new_version = self.store.compare_and_commit(version, proposed)
                    verdict, reason = ((Verdict.V, "Validated and committed") if committed
                                       else (Verdict.U, "Concurrent update; revalidate"))
            record = {"from_version": version, "version": new_version, "verdict": verdict.value,
                      "reason": reason, "committed": committed, "contracts": outcomes, "reassessment": reassessment}
            self.history.append(record)
            return record
