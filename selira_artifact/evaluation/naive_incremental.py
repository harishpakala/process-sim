"""RC02 evaluation-only direct-change comparator for the historical SC01 workload."""
import itertools
import json
from collections import Counter

from selira.runtime.reassessment.snapshot import Snapshot, check
from selira.runtime.reassessment.selective_sc01 import compare


def compare_naive(before, after, *, coverage_attested=True,
                  policy_unchanged=True, authority_unchanged=True):
    reference = compare(
        before, after, coverage_attested=coverage_attested,
        policy_unchanged=policy_unchanged,
        authority_unchanged=authority_unchanged)
    universe = set(before.assigned) | set(after.assigned)
    affected = {
        asset for asset in universe
        if before.assigned.get(asset) != after.assigned.get(asset)
    }
    if reference.full_fallback or before.complete != after.complete:
        affected = universe
    naive = {
        asset: check(after if asset in affected else before, asset)
        for asset in sorted(universe)
    }
    disagreements = [
        {"asset": asset, "full": reference.full[asset], "naive": naive[asset]}
        for asset in sorted(universe) if naive[asset] != reference.full[asset]
    ]
    return {
        "full_evaluations": reference.full_evaluations,
        "dsr_evaluations": reference.selective_evaluations,
        "nir_evaluations": len(affected),
        "dsr_equivalent": reference.equivalent,
        "nir_equivalent": not disagreements,
        "disagreements": disagreements,
    }


def bounded():
    states = [
        Snapshot("R1", {"asset:A": a} if a is not None else {},
                 {k: v for k, v in zip(("catalog:1", "catalog:2"), (x, y))
                  if v is not None}, complete=True)
        for a, x, y in itertools.product(
            (None, "id:x", "id:y", "id:z"),
            (None, "id:x", "id:y"), (None, "id:x", "id:y"))
    ]
    totals = Counter()
    disagreements = Counter()
    for old, new in itertools.product(states, repeat=2):
        result = compare_naive(
            old, Snapshot("R2", new.assigned, new.catalog, new.complete))
        totals["comparisons"] += 1
        for key in ("full_evaluations", "dsr_evaluations", "nir_evaluations",
                    "dsr_equivalent", "nir_equivalent"):
            totals[key] += result[key]
        for row in result["disagreements"]:
            disagreements[(row["full"], row["naive"])] += 1
    assert totals["comparisons"] == 1296
    assert totals["full_evaluations"] == 1215
    assert totals["dsr_evaluations"] == 1084
    assert totals["dsr_equivalent"] == 1296
    return {"snapshots": len(states), **totals,
            "disagreements": [
                {"full": full, "naive": naive, "count": count}
                for (full, naive), count in sorted(disagreements.items())],
            "scope": "Logical target evaluations; prior evaluation excluded"}


if __name__ == "__main__":
    print(json.dumps(bounded(), indent=2))
