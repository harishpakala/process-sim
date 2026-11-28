"""RC02 graph comparator: logical outcome reuse, not incremental SHACL."""
from selira.runtime.reassessment.selective import project, compare


def select_naive(before, after, old, new, *, full_fallback):
    universe = old.keys() | new.keys()
    if full_fallback:
        return set(universe)
    modified = {str(s) for s, _, _ in set(before) ^ set(after)}
    scope = old.keys() ^ new.keys()
    return {k for k in universe if k in scope or k[1] in modified}


def compare_graph(before, after, contracts, outcome_oracle, **reuse):
    """Use independently supplied full outcome maps; count logical target work."""
    old, _ = project(before, contracts)
    new, _ = project(after, contracts)
    universe = old.keys() | new.keys()
    dsr = compare(before, after, contracts, **reuse)
    selected = select_naive(before, after, old, new,
                            full_fallback=dsr["full_fallback"])
    prior = outcome_oracle(before)
    full = outcome_oracle(after)
    assert set(prior) == set(old)
    assert set(full) == set(new)
    naive = {k: (full if k in selected else prior).get(k, "NA")
             for k in universe}
    disagreements = [
        {"contract": k[0], "focus": k[1],
         "full": full.get(k, "NA"), "naive": naive[k]}
        for k in sorted(universe) if naive[k] != full.get(k, "NA")]
    return dict(full_evaluations=dsr["full_evaluations"],
                dsr_evaluations=dsr["selective_evaluations"],
                nir_evaluations=len(selected),
                dsr_equivalent=dsr["equivalent"],
                nir_equivalent=not disagreements,
                disagreements=disagreements)
