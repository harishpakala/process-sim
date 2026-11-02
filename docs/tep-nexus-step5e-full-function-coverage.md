# Step 5E — evidence-derived full-function benchmark

**Status:** implementation committed; local execution pending.

The expanded benchmark is derived from the same run-scoped, provisional engineering-function registry used by the query planner. It does not guess identifiers. It preserves the seven positive and two negative baseline cases, then adds a positive case for each other supported function. With the previously observed 34-function registry, this yields **36 total cases (34 positive + 2 negative)**, of which **27 are new**.

## Local PowerShell commands

```powershell
git pull --ff-only
python -m unittest discover -s tests -p "test_tep_nexus_*.py" -v

python scripts\tep_nexus_expand_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --output reports\tep_nexus_benchmark_full_coverage_cases.json
```

The generator requires exactly 34 supported functions by default and refuses to proceed if any baseline positive function is no longer eligible. If it fails, inspect mapping discovery and temporal coverage; do not override the count merely to force a pass.

Before running all 36 cases, consider a controlled pilot with a selected few new function identifiers. Full smoke run:

```powershell
python scripts\tep_nexus_benchmark.py `
  --fixtures reports\tep_nexus_benchmark_full_coverage_cases.json `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --repeats 1 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_full_coverage_summary.json
```

Expected: 36 executions. Estimated time ~25–35 minutes given previous successful-case latency; this is an estimate, not a guarantee.

Do not commit raw operational reports or unsanitized mapping snapshots. The sanitized benchmark summary is suitable for review after checking its contents.

## Interpretation

Passing all cases establishes limited-scope validated query completion for each eligible function in this particular local run. It does not independently verify physical sensor binding, common simulation provenance, or correctness beyond the implemented answer checks.

Next after full coverage: targeted negative/boundary tests and stage-level latency diagnostics. The prior proposal of ~50 additional tests was an estimate, not a fixed requirement; 27 new full-coverage cases are implemented here.
