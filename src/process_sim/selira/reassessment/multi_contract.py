"""Selective logical reference reassessment; not incremental SHACL."""
from rdflib import RDF, URIRef


def project(graph, contracts):
    assigned, index = {}, {}
    for key, (entry, _) in contracts.items():
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


def compare(before, after, contracts, *, coverage_attested=False,
            policy_unchanged=False, authority_unchanged=False):
    old, oi = project(before, contracts)
    new, ni = project(after, contracts)
    universe = old.keys() | new.keys()
    fallback = not (coverage_attested and policy_unchanged and authority_unchanged)
    changed = {k for k in oi.keys() | ni.keys() if oi.get(k, set()) != ni.get(k, set())}
    affected = {k for k in universe if fallback or old.get(k) != new.get(k)
                or (k[0], old.get(k)) in changed or (k[0], new.get(k)) in changed}

    def check(k, assignments, index):
        if k not in assignments:
            return "NA"
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
