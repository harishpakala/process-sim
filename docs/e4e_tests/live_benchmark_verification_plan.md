# TEP NEXUS benchmark verification — audit stage

The committed live benchmark summary is `reports/tep_nexus_benchmark_full_coverage_summary.json`.
Its declared scope is `operator_local_execution_not_independent_provenance_verification`.
Do not interpret 36/36 as independent semantic or historian correctness.

## Reproduce the summary audit

```bash
python scripts/audit_tep_nexus_benchmark.py \
  --summary reports/tep_nexus_benchmark_full_coverage_summary.json \
  --output reports/tep_nexus_benchmark_audit.json
```

The script checks case counts, unique IDs, completed/rejected statuses, repairs,
initial failed checks, and overall latency distribution. No external packages needed.

## Independent SQL oracle — required next step

1. Locate the live benchmark runner and actual TimescaleDB table/column names.
2. Capture each live result's `case_id`, `run_id`, `signal_id`,
   `simulation_time`, and `value` into `benchmark_observed.csv`.
3. Using a **separate SQL query**, independent of the function registry, planner,
   query builders, and pipeline validators, query TimescaleDB for expected values.
   Export to `oracle_expected.csv` with identical column names.
4. Compare exact row multisets:

```bash
python scripts/audit_tep_nexus_benchmark.py \
  --summary reports/tep_nexus_benchmark_full_coverage_summary.json \
  --expected-csv oracle_expected.csv \
  --actual-csv benchmark_observed.csv
```

The comparison uses exact serialized strings and counts duplicates. Define and
document a numeric serialization policy before producing CSVs; do not silently
round or coerce values to manufacture equality. Preserve the independent SQL,
database snapshot identity, and exports as reproducibility artifacts.

**Not yet done:** Independent SQL extraction, independent mapping fixture,
stage-level latency instrumentation, or rerunning new negative cases. The summary
does not contain sufficient information to claim any of these have passed.

## Negative cases to add to the live runner

| Scenario | Expected behavior |
|---|---|
| Unknown function | Explicit rejection (already tested) |
| Conflicting identifiers | Explicit rejection (already tested) |
| Missing mapping | Explicit unresolved-mapping error; no guessed signal |
| Ambiguous mapping | Explicit ambiguity; no arbitrary selection |
| Changed/stale mapping | Deterministic mismatch detection or documented refresh |
| Unknown run ID | No cross-run fallback or fabricated observations |
| Truncated result | Explicit truncation/limit metadata, no completeness claim |

Use isolated fixtures or transactions for mapping mutations. Do not alter the
production engineering graph during tests.

## Stage latency to instrument

Record monotonic durations for model planning, plan validation, graph mapping
resolution, historian SQL execution, evidence validation/repair, and answer
rendering. Also record total wall time, model/version, run ID, case ID, repeat
index, and whether repair was invoked. Report median and p95 per stage.

## Reporting discipline

Primary result currently: 36/36 **pipeline-accepted** cases (34 completed,
2 expected rejections), not 36/36 independently oracle-validated cases.
Grounded Q1--Q12 remains a secondary development-set QA assessment.
