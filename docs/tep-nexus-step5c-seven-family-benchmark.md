# TEP NEXUS — Step 5C seven-family benchmark checkpoint

**Status:** committed; local verification pending.

The benchmark fixture now contains seven positive cases spanning FI, LI, PI, TI, JI, SC and VC, plus two negative cases (unsupported FI_999 and conflicting FI_101/VC_101). Each positive case requests the latest measurement, a 10-simulation-minute trend, associated asset and provenance. These identifiers were listed in the previously operator-supplied 34-function supported registry; their current eligibility still depends on local mapping discovery and temporal coverage.

## PowerShell commands

```powershell
git status
git branch --show-current
git pull --ff-only

python -m unittest discover `
  -s tests `
  -p "test_tep_nexus_*.py" `
  -v

python scripts\tep_nexus_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --repeats 1 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_seven_families_summary.json
```

**Expected:** 65 offline tests (previously 63 plus two new fixture tests) and nine benchmark executions. This is not a claim of execution success.

Run the nine-case smoke test before a three-repeat benchmark. If the smoke test passes, execute:

```powershell
python scripts\tep_nexus_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --repeats 3 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_seven_families_repeated_summary.json
```

**Expected:** 27 case executions. Given previous local timings, this may take approximately 10–15 minutes. The benchmark validates selected numeric claims and caveats, not arbitrary physical truth, sensor binding, or shared run provenance. Individual per-case reports may include operational evidence and must not be committed without sanitization.

Upload the summary JSON and local test result for review. If any case fails, inspect its local raw report and share only sanitized error details.
