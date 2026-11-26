"""Version-bound selective SHACL admission for the supported lexical fragment.

Full snapshot projection remains necessary. Cache is in-memory, not durable.
"""
from time import perf_counter
from rdflib import Graph, URIRef, RDF
from rdflib.namespace import SH
from pyshacl import validate
from .automation_manager import MultiContractAutomationManager
from .reassessment.selective import project, select

class SelectiveAutomationManager(MultiContractAutomationManager):
    def __init__(self, artifacts):
        super().__init__(artifacts)
        self._cache = None

    def submit(self, candidate, *, expected_version, evidence_complete=(),
               identity_normalized=False, applicability_confirmed=False,
               coverage_attested=False, policy_unchanged=False, authority_unchanged=False):
        started = perf_counter()
        with self._lock:
            _, version = self.store.snapshot()
            proposed = Graph() + candidate
            evidence = set(evidence_complete)
            outcomes, qualified = {}, {}
            executed = reused = calls = 0
            fallback = True
            committed = False
            new_version = version
            if version != expected_version:
                verdict, reason = "U", "Stale snapshot version"
            else:
                eligible = {}
                projections = {}
                for key, (entry, ttl) in self._contracts.items():
                    try:
                        if not identity_normalized or not applicability_confirmed or not set(entry["requires_complete"]) <= evidence:
                            raise ValueError("Missing evidence")
                        a, i = project(proposed, {key: (entry, ttl)})
                        # String keys are safe only for URI resources in this fragment.
                        fp = URIRef(entry["focus_predicate"])
                        if any(not isinstance(n, URIRef) for n in proposed.subjects(fp, None)):
                            raise ValueError("Non-IRI focus")
                        eligible[key] = (entry, ttl)
                        projections[key] = (a, i)
                    except Exception as exc:
                        outcomes[key] = {"id": entry["id"], "verdict": "U", "reason": str(exc), "violations": []}
                new = {k:v for a,i in projections.values() for k,v in a.items()}
                ni = {k:v for a,i in projections.values() for k,v in i.items()}
                affected = set(new)
                prior = {}
                if self._cache is not None and self._cache[0] == version and len(eligible) == len(self._contracts):
                    _, old, oi, prior = self._cache
                    try:
                        affected, fallback = select(old, oi, new, ni,
                            coverage_attested=coverage_attested, policy_unchanged=policy_unchanged,
                            authority_unchanged=authority_unchanged)
                        affected |= set(new) - prior.keys()
                    except Exception:
                        affected, fallback = set(new), True
                for key, (entry, ttl) in eligible.items():
                    keys = {k for k in new if k[0] == key}
                    selected = keys & affected
                    try:
                        if selected:
                            shapes = Graph().parse(data=ttl, format="turtle")
                            shape = URIRef(key)
                            shapes.remove((shape, SH.targetSubjectsOf, None))
                            for k in selected:
                                shapes.add((shape, SH.targetNode, URIRef(k[1])))
                            executed += len(selected)
                            calls += 1
                            conforms, report, _ = validate(proposed, shacl_graph=shapes, inference="none", advanced=False, abort_on_first=False)
                            actual = {str(n) for n in report.objects(None, SH.focusNode)}
                            expected = {k[1] for k in selected if len(ni.get((key,new[k]),set())) != 1}
                            if actual != expected or bool(conforms) != (not expected):
                                raise ValueError("Selected SHACL/reference disagreement")
                            qualified.update({k: "F" if k[1] in actual else "V" for k in selected})
                        for k in keys - selected:
                            qualified[k] = prior[k]
                            reused += 1
                        violations = sorted(k[1] for k in keys if qualified[k] == "F")
                        outcomes[key] = {"id": entry["id"], "verdict": "F" if violations else "V" if keys else "NA",
                                         "violations": violations, "focus_count": len(keys)}
                    except Exception as exc:
                        outcomes[key] = {"id": entry["id"], "verdict": "U", "reason": str(exc), "violations": []}
                values = {r["verdict"] for r in outcomes.values()}
                verdict = "F" if "F" in values else "U" if "U" in values else "NA" if values == {"NA"} else "V"
                reason = "Qualified candidate" if verdict == "V" else "Candidate not admitted"
                if verdict == "V":
                    committed, new_version = self.store.compare_and_commit(version, proposed)
                    if committed:
                        self._cache = (new_version, new, ni, qualified)
                    else:
                        verdict, reason = "U", "Concurrent update"
            record = {"from_version": version, "version": new_version, "verdict": verdict,
                      "reason": reason, "committed": committed, "contracts": outcomes,
                      "executed_instances": executed, "reused_instances": reused,
                      "shacl_calls": calls, "full_fallback": fallback,
                      "elapsed_seconds": perf_counter()-started}
            self.history.append(record)
            return record
