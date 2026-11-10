# Deterministic-only TEP NEXUS baseline

This benchmark uses the **same fixture cases** as the existing LLM benchmark, but takes the engineering function and query parameters from a structured fixture rather than from Ollama. It uses the existing function registry, GraphDB mapping resolution, TimescaleDB retrieval, evidence construction and deterministic evidence-only answer reconstruction/validation.

## Run locally

Start GraphDB and TimescaleDB, configure the run-specific mapping-discovery and temporal-coverage files, and set the historian DSN. From the repository root in PowerShell:

```powershell
$env:TEP_TIMESCALE_DSN="postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus"
python scripts/tep_nexus_deterministic_baseline.py --run-id YOUR_RUN_ID --repeats 3
```

The command writes `reports/deterministic_baseline_results.json` and `reports/deterministic_baseline_cases.csv`. It exits nonzero if any case fails. The run ID must match a locally available simulation/historian run; **no live measurements have been executed or verified as part of this commit**.

The script checks the two expected rejection cases using the same explicit identifier and error-message constraints as the existing fixture. It reports per-case stage times, elapsed time, outcomes and aggregate median/p95 latency.

## Interpretation

- This is a **structured-request, deterministic-answer baseline**, not a natural-language understanding benchmark. A model's ability to identify a function from paraphrases must be evaluated separately.
- It does **not** construct or benchmark the VTKG. The repository already has a separate paired VTKG/direct retrieval harness: `scripts/tep_nexus_baseline_comparison.py`.
- Comparisons to previously published 44.062-second or 58.180-second medians are descriptive only unless workload, run, hardware, service state, and repetitions are controlled.
- The mapping registry is provisional; agreement with historian observations does not independently establish physical sensor identity.
- Do not publish numerical results until the local services have been run and the output artifacts audited.
