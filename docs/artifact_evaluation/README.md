# TEP NEXUS — 36-case benchmark and artifact evaluation

This is the entry point for reviewing and reproducing the **Step 5E evidence-derived, full-function benchmark**. The benchmark tests run-scoped engineering-function query planning and limited-scope answer validation. It is **not a fault-injection tutorial**. For simulation Start/Stop/Reset and the **Fault-01 bias on XMEAS9** Web UI example, see the [root README](../../README.md#operate-the-simulation-and-faults-from-the-web-ui).

> **Evidence status:** The [Step 5E checkpoint](../research/tep-nexus/tep-nexus-step5e-full-function-coverage.md) records the implementation as committed but **local execution pending**. The **36 cases are the intended suite size**, not 36 independently verified passes. Do not report a success rate or execution time without an actual, inspected benchmark summary.

## 1. Benchmark scope

The expanded suite is generated from the run-scoped, provisional engineering-function registry. The previously observed registry contained **34 supported functions**. The suite retains seven positive and two negative baseline cases and adds 27 positive cases, yielding **34 positive + 2 negative = 36 cases** when the expected registry is available.

| Case group | Count | Expected behavior |
| --- | ---: | --- |
| Supported engineering functions | 34 | Complete the query with the requested measurement, ten-simulation-minute trend, associated asset and provenance; pass the implemented limited-scope answer checks |
| Unsupported or conflicting function requests | 2 | Reject for the intended validation reason, rather than a service outage or model-formatting error |
| **Total** | **36** | **Expected suite size, not a measured result** |

The seven baseline positive function families are FI, LI, PI, TI, JI, SC and VC. The two negative baseline cases cover an unsupported function (`FI_999`) and a conflicting function selection (`FI_101` versus `VC_101`). The registry and fixture set are specific to the selected run; the generator must not invent or silently drop function identities.

The historical Fault-02 Q1–Q10 LLM evaluation is **a different experiment**, not part of these 36 cases. Its [original reviewer guide](../e4e_tests/fault02_artifact_evaluation_guide_archived.md) and [evaluation findings](../e4e_tests/fault02_final_evaluation_and_paper_findings.md) remain archived for provenance.

## 2. What a reviewer needs

- A checkout of a pinned source commit; record `git rev-parse HEAD`, Python version, operating environment and model identifier. A moving branch name alone is not a reproducible source version.
- Python dependencies and a functioning local query-planner environment, including the model/service configured for `scripts/tep_nexus_ollama_query_planner.py`.
- Run-specific mapping-discovery and temporal-coverage snapshots, plus access to the GraphDB/TimescaleDB evidence needed by the planner. The benchmark generator itself reads local snapshots and **does not connect to GraphDB, TimescaleDB or Ollama**.
- A verified historian run with eligible functions. The run ID below is the one named in the Step 5E checkpoint; a fresh database will **not** contain that run automatically.

The local paths `reports/tep_nexus_mapping_discovery.json` and `reports/tep_nexus_temporal_coverage.json` must describe the **same selected run**. The fixture generator checks for exactly 34 eligible functions by default and fails if baseline positive functions are missing. If the count differs, investigate the underlying snapshots; do not override the check merely to obtain 36 cases.

For local infrastructure startup, use the [root README](../../README.md#local-startup-windows-powershell). Starting services does not restore historical data.

## 3. Generate the 36-case fixture

From the repository root in Windows PowerShell, using a source checkout and local snapshots that have been verified for the selected run:

```powershell
git rev-parse HEAD
python --version

python -m unittest discover -s tests -p "test_tep_nexus_*.py" -v

python scripts\tep_nexus_expand_benchmark.py `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --output reports\tep_nexus_benchmark_full_coverage_cases.json
```

Inspect the generated JSON before running it. **Expected, conditional on a valid 34-function registry:** 36 fixtures comprising 34 positive and two negative cases. The generator's output is a constructed test set, **not a benchmark execution result**.

## 4. Run the benchmark

A controlled pilot with a few new supported functions is advisable before the full suite. The full one-repeat smoke run documented in Step 5E is:

```powershell
python scripts\tep_nexus_benchmark.py `
  --fixtures reports\tep_nexus_benchmark_full_coverage_cases.json `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --repeats 1 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_full_coverage_summary.json
```

The runner writes a sanitized summary to the supplied `--summary` path and per-case planner reports under `reports/tep_nexus_benchmark_runs/` by default. It reports total, passed, failed, per-case classifications, elapsed time, available stage timings, answer-validation status and repair metadata. A nonzero exit code indicates at least one failed case.

The Step 5E estimate of **25–35 minutes** for 36 executions is a planning estimate, **not an observed measurement**. For repeated trials, specify `--repeats N` and report the resulting total as **36 × N executions**, not N new distinct questions.

## 5. How to interpret the results

A positive case passes the runner's checks only when the planner completes, selects the expected engineering function, reports `CHECKS_PASSED_LIMITED_SCOPE` and has no failed implemented answer checks. A negative case passes only when it fails at the intended validation stage with the required rejection reason; an unrelated timeout or Ollama planning failure is not a correct rejection.

**Passing the harness does not establish** independently verified physical sensor installation, full cross-system provenance, arbitrary factual correctness, or causal attribution of measurement changes. A reported `COMPLETED` status without the required validation fields is not sufficient for a positive-case pass.

Review the sanitized summary, investigate failures using local reports, and distinguish pipeline completion from independent engineering ground truth. Do not commit unsanitized operational reports or mapping snapshots.

## 6. Reproducibility checklist

- [ ] Pin source commit, Python/runtime versions, model version and service configuration.
- [ ] Record the selected run ID and verify the mapping and temporal-coverage snapshot provenance.
- [ ] Record the supported-function count and SHA-256 hashes of the snapshots and generated fixture JSON.
- [ ] Confirm 34 positive and two negative fixtures, or document why the prerequisites are not met.
- [ ] Execute offline tests and the benchmark; preserve command lines, exit codes and sanitized summary.
- [ ] Report actual passed/failed counts, case classifications, timings and limitations **only after execution**.
- [ ] Deposit a versioned, privacy-reviewed artifact bundle with hashes and clear instructions for restoring any run-specific data needed by independent reviewers.

## 7. Related research documentation

- [Step 5E — full-function benchmark design and commands](../research/tep-nexus/tep-nexus-step5e-full-function-coverage.md)
- [Step 5C — seven-family baseline](../research/tep-nexus/tep-nexus-step5c-seven-family-benchmark.md)
- [Repeated benchmark and rejection classification](../research/tep-nexus/tep-nexus-step5-repeated-benchmark-checkpoint.md)
- [Research evaluation strategy](../research/evaluation-strategy.md)
- [Archived Fault-02 reviewer guide](../e4e_tests/fault02_artifact_evaluation_guide_archived.md) — historical experiment only; not required to operate or run the 36-case suite

**Current publication boundary:** This document specifies how to attempt the 36-case benchmark. It does not claim that an independently reproducible bundle, successful 36-case execution, or physical-world validation has been demonstrated.
