"""Generate an expanded benchmark from run-scoped supported functions.

This command never connects to GraphDB, TimescaleDB or Ollama. It reads local
mapping and coverage snapshots and refuses to silently drop baseline cases.
"""

# Created: 2026-11-02
# Author: Harish
import argparse
import json
from pathlib import Path

from tep_nexus_function_registry import load_supported_functions


def expand_fixtures(baseline, supported):
    if not isinstance(baseline, list) or not baseline:
        raise ValueError("Baseline fixtures must be a nonempty list")
    ids = [case["id"] for case in baseline]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate baseline case identifiers")
    existing = {case["function"] for case in baseline if case["expected"] == "complete"}
    missing = existing - set(supported)
    if missing:
        raise ValueError("Baseline positive functions missing from registry: " + ", ".join(sorted(missing)))
    additional = []
    for function in sorted(set(supported) - existing):
        additional.append({
            "id": "coverage_" + function.lower(),
            "function": function,
            "question": (
                f"For engineering function {function}, show the latest measurement "
                "and the trend over the last 10 simulation minutes, including "
                "the associated asset and provenance."
            ),
            "expected": "complete",
        })
    return baseline + additional


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--baseline", default="tests/fixtures/tep_nexus_benchmark_cases.json")
    parser.add_argument("--output", default="reports/tep_nexus_benchmark_full_coverage_cases.json")
    parser.add_argument("--expected-supported-count", type=int, default=34)
    args = parser.parse_args()
    registry = load_supported_functions(args.mapping_discovery, args.temporal_coverage, args.run_id)
    if len(registry) != args.expected_supported_count:
        parser.error(f"Expected {args.expected_supported_count} supported functions, found {len(registry)}")
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8-sig"))
    expanded = expand_fixtures(baseline, registry)
    positive = [case for case in expanded if case["expected"] == "complete"]
    if len(positive) != len(registry):
        parser.error("Positive fixture count does not equal supported registry size")
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(expanded, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(expanded)} cases: {len(positive)} supported, "
          f"{len(expanded) - len(positive)} negative; added {len(expanded) - len(baseline)} cases")
    print(f"Output: {destination}")


if __name__ == "__main__":
    main()
