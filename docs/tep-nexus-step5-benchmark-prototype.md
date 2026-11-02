# TEP NEXUS — Step 5 benchmark prototype

The benchmark runner is **implemented but not yet locally executed**. It uses the existing read-only planner, Ollama, GraphDB, and TimescaleDB. The fixture suite contains three positive queries (FI_101, VC_101, TI_101) and two negative queries (unsupported FI_999 and multi-identifier FI_101 + VC_101).

## Local PowerShell verification

```powershell
git status
git branch --show-current
git pull --ff-only

python -m unittest discover `
  -s tests `
  -p "test_tep_nexus_*.py" `
  -v

python scripts\tep_nexus_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b
```

The test suite should now contain **61 tests** if the previous 57 and four new benchmark tests are all discovered. This is an expectation, not a verified result.

The benchmark writes a sanitized aggregate to `reports/tep_nexus_benchmark_summary.json`. Individual case reports are written to `reports/tep_nexus_benchmark_runs/` and **may contain operational evidence and asset identifiers**; do not commit those raw reports. Review the summary before sharing it.

A positive case passes only when the pipeline completes, the planned function matches, and all implemented answer checks pass. A negative case passes only if the pipeline returns an error **before retrieving evidence**. These tests do not certify physical sensor mapping or source-system provenance.

The current runner is a first checkpoint, not a full research benchmark: it does not yet evaluate latency percentiles, repeated-run stability, accuracy against independent ground truth, or all 34 function identifiers. Results will depend on the local Ollama model and service state. If a fixture fails, retain its local case report for debugging, but sanitize before sharing.
