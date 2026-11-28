"""RC02 evaluation-only comparison on the unchanged integrated lifecycle."""
import json
from collections import Counter
from unittest.mock import patch

from rdflib import Graph
import multi_contract_lifecycle as lifecycle
from compare_reassessment import select_naive
from selira.runtime.reassessment.selective import project


def run():
    original_factory = lifecycle.MultiContractAutomationManager.from_directory
    rows = []
    prior_outcomes = None

    def factory(*args, **kwargs):
        manager = original_factory(*args, **kwargs)
        original_submit = manager.submit

        def outcomes(graph, result):
            assigned, _ = project(graph, manager._contracts)
            return {k: ("F" if k[1] in result["contracts"][k[0]]["violations"]
                        else "V") for k in assigned}

        def submit(candidate, *args, **kwargs):
            nonlocal prior_outcomes
            before, _ = manager.store.snapshot()
            candidate_copy = Graph()
            candidate_copy += candidate
            result = original_submit(candidate, *args, **kwargs)
            report = result["reassessment"]
            if report is not None:
                assert prior_outcomes is not None
                old, _ = project(before, manager._contracts)
                new, _ = project(candidate_copy, manager._contracts)
                full = outcomes(candidate_copy, result)
                assert set(prior_outcomes) == set(old)
                universe = old.keys() | new.keys()
                selected = select_naive(before, candidate_copy, old, new,
                                        full_fallback=report["full_fallback"])
                naive = {k: (full if k in selected else prior_outcomes).get(k, "NA")
                         for k in universe}
                differences = [
                    dict(contract=k[0], focus=k[1],
                         full=full.get(k, "NA"), naive=naive[k])
                    for k in sorted(universe) if naive[k] != full.get(k, "NA")]
                assert len(universe) == report["full_evaluations"]
                rows.append(dict(full_evaluations=report["full_evaluations"],
                                 dsr_evaluations=report["selective_evaluations"],
                                 nir_evaluations=len(selected),
                                 dsr_equivalent=report["equivalent"],
                                 nir_equivalent=not differences,
                                 full_fallback=report["full_fallback"],
                                 disagreements=differences))
            if result["committed"]:
                prior_outcomes = outcomes(candidate_copy, result)
            return result

        manager.submit = submit
        return manager

    # Temporary instrumentation only; no change to runtime or original workload.
    with patch.object(lifecycle.MultiContractAutomationManager,
                      "from_directory", side_effect=factory):
        original = lifecycle.run()
    events = [e for e in original["events"] if e["reassessment"] is not None]
    assert len(rows) == len(events) == 13
    for row, event in zip(rows, events):
        row["event"] = event["event"]
    summary = original["summary"]
    assert (summary["events"], summary["admitted"], summary["rejected"],
            summary["deferred"]) == (16, 7, 8, 1)
    totals = Counter()
    differences = Counter()
    for row in rows:
        for key in ("full_evaluations", "dsr_evaluations", "nir_evaluations",
                    "dsr_equivalent", "nir_equivalent"):
            totals[key] += row[key]
        for d in row["disagreements"]:
            differences[(d["full"], d["naive"])] += 1
    assert totals["full_evaluations"] == summary["full_evaluations"] == 2444
    assert totals["dsr_evaluations"] == summary["selective_evaluations"] == 203
    assert totals["dsr_equivalent"] == 13
    return dict(comparisons=len(rows), **totals,
                disagreements=[dict(full=f, naive=n, count=c)
                               for (f, n), c in sorted(differences.items())],
                events=rows, original_summary=summary,
                scope="Graph outcomes; logical instance evaluations; actual admission unchanged")


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
