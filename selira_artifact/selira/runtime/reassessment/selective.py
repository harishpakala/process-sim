"""Selective logical reference reassessment; not incremental SHACL."""
from rdflib import RDF, URIRef
from rdflib.util import from_n3
from pathlib import Path
from ..policy_executor import PolicyExecutor
from ..policy_evaluator import load_policy, evaluate_policy
from selira.formal.identifier_comparison import compare_fields


def project(graph, contracts):
    assigned, index = {}, {}
    for key, (entry, _) in contracts.items():
        if entry.get("kind") == "standalone_match":
            fp = URIRef(entry["focus_predicate"])
            left = URIRef(entry["left_predicate"])
            right = URIRef(entry["right_predicate"])
            for node in set(graph.subjects(fp, None)):
                assigned[key, str(node)] = (
                    tuple(sorted(v.n3() for v in graph.objects(node, left))),
                    tuple(sorted(v.n3() for v in graph.objects(node, right))),
                )
            continue
        fp, tp, tc = (URIRef(entry[k]) for k in
                      ("focus_predicate", "catalog_predicate", "catalog_class"))
        for nodes, predicate, is_focus in (
                (set(graph.subjects(fp, None)), fp, True),
                (set(graph.subjects(RDF.type, tc)), tp, False)):
            for node in nodes:
                values = set(graph.objects(node, predicate))
                if len(values) != 1 or not str(next(iter(values), "")).strip():
                    raise ValueError("Unsupported identifier cardinality")
                value = str(next(iter(values)))
                if is_focus:
                    assigned[key, str(node)] = value
                else:
                    index.setdefault((key, value), set()).add(node)
    return assigned, index


def relevant_dependency_changed(key, old, new, changed):
    """Include scope entry/exit, projected values and both lookup scopes."""
    return (old.get(key) != new.get(key)
            or (key[0], old.get(key)) in changed
            or (key[0], new.get(key)) in changed)


def select(old, oi, new, ni, *, coverage_attested=False,
            policy_unchanged=False, authority_unchanged=False, policy_paths=None, policy_executor=None):
    universe = old.keys() | new.keys()
    fallback = not (coverage_attested and policy_unchanged and authority_unchanged)
    changed = {k for k in oi.keys() | ni.keys() if oi.get(k, set()) != ni.get(k, set())}
    if policy_executor is not None or policy_paths is None:
        executor = policy_executor or PolicyExecutor(Path(__file__).resolve().parents[3])
        affected = set()
        for k in universe:
            context, _ = executor.dispatch("DependencyProjectionCompleted", {
                "evidence.coverage_attested": coverage_attested,
                "context.policy_unchanged": policy_unchanged,
                "context.authority_unchanged": authority_unchanged,
                "dependency.changed": relevant_dependency_changed(k, old, new, changed),
            })
            reassess = context.get("selection.reassess")
            reuse = context.get("selection.reuse")
            if type(reassess) is not bool or type(reuse) is not bool or reassess == reuse:
                raise ValueError("Missing or inconsistent policy selection")
            if not reassess and (fallback or relevant_dependency_changed(k, old, new, changed)):
                raise ValueError("Unsafe reuse decision")
            if reassess:
                affected.add(k)
        return affected, fallback
    # Compatibility for explicit legacy policy path callers.
    policy_dir = Path(__file__).resolve().parents[3] / "policies"
    impact_path, selection_path = policy_paths if policy_paths is not None else (
        policy_dir / "LP-03.safsl", policy_dir / "LP-04.safsl")
    impact = load_policy(Path(impact_path))
    selection = load_policy(Path(selection_path))
    attestations = {"CoverageAttested": coverage_attested,
                    "PolicyUnchanged": policy_unchanged,
                    "AuthorityUnchanged": authority_unchanged}
    affected = set()
    for k in universe:
        decision = evaluate_policy(impact, {
            **attestations,
            "RelevantDependencyChanged": relevant_dependency_changed(k, old, new, changed),
        })
        selected = evaluate_policy(selection, {**attestations, **decision})
        if selected["Reassess"] == selected["Reuse"]:
            raise ValueError("Inconsistent policy selection")
        if selected["Reassess"]:
            affected.add(k)

    return affected, fallback

def compare(before, after, contracts, *, coverage_attested=False,
            policy_unchanged=False, authority_unchanged=False, policy_paths=None, policy_executor=None):
    old, oi = project(before, contracts)
    new, ni = project(after, contracts)
    universe = old.keys() | new.keys()
    affected, fallback = select(old, oi, new, ni, coverage_attested=coverage_attested,
                                policy_unchanged=policy_unchanged, authority_unchanged=authority_unchanged,
                                policy_paths=policy_paths, policy_executor=policy_executor)
    def check(k, assignments, index):
        if k not in assignments:
            return "NA"
        entry = contracts[k[0]][0]
        if entry.get("kind") == "standalone_match":
            left, right = assignments[k]
            if len(left) != 1 or len(right) != 1:
                return "F"
            policy = entry["comparison_policy"]
            if policy["kind"] not in ("normalized_asset_identifier", "lexical_equality"):
                raise ValueError("Unsupported identifier comparison policy")
            try:
                valid = compare_fields(str(from_n3(left[0])), str(from_n3(right[0])), policy)
            except ValueError:
                valid = False
            return "V" if valid else "F"
        return "V" if len(index.get((k[0], assignments[k]), set())) == 1 else "F"

    prior = {k: check(k, old, oi) for k in universe}
    selective = {k: check(k, new, ni) if k in affected else prior[k] for k in universe}
    full = {k: check(k, new, ni) for k in universe}
    return {"affected": [list(k) for k in sorted(affected)],
            "selective_evaluations": len(affected), "full_evaluations": len(universe),
            "equivalent": selective == full, "full_fallback": fallback,
            "by_contract": {key: {"selective": sum(k[0] == key for k in affected),
                                  "full": sum(k[0] == key for k in universe)}
                            for key in contracts}}
