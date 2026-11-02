# TEP NEXUS — Step 5 repeated benchmark and rejection classification

This checkpoint is **committed but not yet locally verified**.

The benchmark now optionally repeats all cases, records repeat numbers, prevents stale per-case JSON from being reused, classifies subprocess timeouts, and requires specific validation errors for negative fixtures.

## PowerShell

```powershell
git pull --ff-only

python -m unittest discover `
  -s tests `
  -p "test_tep_nexus_*.py" `
  -v

python scripts\tep_nexus_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --repeats 3 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_repeated_summary.json
```

Expected offline count: **63** (61 previously reported plus two new tests). Expected benchmark cases: **15** (five fixtures repeated three times). These counts are expectations, not observed results.

The two negative fixtures require the following explicit error substrings:

- FI_999: `Unsupported engineering function`
- FI_101 and VC_101 together: `Planned engineering function does not match`

A different rejection reason is classified as a failure, even if the pipeline exits nonzero. If an Ollama model fails to generate a plan, that is **not** considered a correct rejection of an unsupported function.

The runner records elapsed seconds per case, but does not yet compute percentile confidence intervals or establish independent ground truth. The JSON summary is sanitized; individual case reports may contain operational identifiers and must not be committed without review.

**Request:** Share the PowerShell test result and `reports/tep_nexus_benchmark_repeated_summary.json` for review.
