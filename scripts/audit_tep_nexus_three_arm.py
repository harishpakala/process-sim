#!/usr/bin/env python3
"""Audit the TEP NEXUS three-arm JSON and compute fixture-clustered intervals.

Python standard library only. Cluster resampling samples distinct positive fixture
IDs with replacement, retaining all repeats within each sampled fixture.
Intervals are percentile bootstrap CIs conditional on this benchmark fixture set.
"""
import argparse
import collections
import json
import math
import random
import statistics
from pathlib import Path


def percentile(values, pct):
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def analyze(data, iterations, seed):
    rows = data["cases"]
    if len({(r["repeat"], r["id"], r["arm"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate case/repeat/arm records")
    expected_arms = ("deterministic", "hybrid", "llm")
    grouped = collections.defaultdict(dict)
    for row in rows:
        if row["arm"] not in expected_arms:
            raise ValueError("Unexpected arm: " + str(row["arm"]))
        grouped[(row["repeat"], row["id"])][row["arm"]] = row
    positives = []
    for (repeat, case_id), arms in grouped.items():
        if set(arms) != set(expected_arms):
            raise ValueError(f"Incomplete triple: {repeat}, {case_id}")
        outcomes = {arms[a]["expected"] for a in expected_arms}
        if len(outcomes) != 1:
            raise ValueError(f"Conflicting expected outcome: {case_id}")
        if outcomes == {"complete"}:
            if not all(arms[a]["passed"] for a in expected_arms):
                raise ValueError(f"Failed positive triple: {repeat}, {case_id}")
            hybrid = arms["hybrid"]["elapsed_seconds"]
            llm = arms["llm"]["elapsed_seconds"]
            if hybrid <= 0:
                raise ValueError("Nonpositive hybrid latency")
            positives.append((case_id, repeat, llm - hybrid, llm / hybrid))
    if not positives:
        raise ValueError("No positive triples")
    by_fixture = collections.defaultdict(list)
    for item in positives:
        by_fixture[item[0]].append(item)
    fixture_ids = sorted(by_fixture)
    rng = random.Random(seed)
    delta_boot, ratio_boot = [], []
    for _ in range(iterations):
        sampled = [rng.choice(fixture_ids) for _ in fixture_ids]
        draws = [row for fixture in sampled for row in by_fixture[fixture]]
        delta_boot.append(statistics.median(r[2] for r in draws))
        ratio_boot.append(statistics.median(r[3] for r in draws))
    arm_stats = {}
    for arm in expected_arms:
        arm_stats[arm] = {}
        for expected in ("complete", "reject"):
            subset = [r for r in rows if r["arm"] == arm and r["expected"] == expected]
            times = [r["elapsed_seconds"] for r in subset]
            arm_stats[arm][expected] = {
                "n": len(subset), "passed": sum(bool(r["passed"]) for r in subset),
                "median_seconds": statistics.median(times) if times else None,
                "p95_seconds": percentile(times, .95) if times else None,
            }
    initial = [r for r in rows if r["arm"] == "llm" and r["expected"] == "complete"]
    failed_counts = [r.get("original_failed_check_count") for r in initial]
    if any(not isinstance(v, int) for v in failed_counts):
        raise ValueError("Missing original_failed_check_count")
    return {
        "source_run_id": data.get("run_id"),
        "case_records": len(rows),
        "positive_triples": len(positives),
        "distinct_positive_fixtures": len(fixture_ids),
        "repeats_per_positive_fixture": dict(collections.Counter(len(v) for v in by_fixture.values())),
        "arms": arm_stats,
        "paired_llm_minus_hybrid_median_seconds": statistics.median(r[2] for r in positives),
        "paired_llm_minus_hybrid_95pct_fixture_cluster_bootstrap_ci_seconds": [
            percentile(delta_boot, .025), percentile(delta_boot, .975)],
        "paired_llm_over_hybrid_median_ratio": statistics.median(r[3] for r in positives),
        "paired_llm_over_hybrid_95pct_fixture_cluster_bootstrap_ci": [
            percentile(ratio_boot, .025), percentile(ratio_boot, .975)],
        "full_llm_initial_positive_answers_with_failed_checks": sum(v > 0 for v in failed_counts),
        "full_llm_initial_failed_checks_total": sum(failed_counts),
        "bootstrap": {"iterations": iterations, "seed": seed, "cluster": "positive fixture ID"},
        "caveats": [
            "Confidence intervals are fixture-clustered descriptive bootstrap intervals, not independent replication across plants or historian snapshots.",
            "Per-check failure categories are not recoverable from aggregate original_failed_check_count; original detailed per-case reports are required.",
            "Deterministic arm uses structured fixture input; other arms interpret natural language.",
            "Recorded final passes represent limited-scope checks and may follow deterministic repair.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261110)
    args = parser.parse_args()
    if args.iterations < 100:
        parser.error("--iterations must be >= 100")
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    result = analyze(data, args.iterations, args.seed)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(output)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
