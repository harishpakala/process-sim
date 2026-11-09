# TEP NEXUS — 36-case benchmark and artifact evaluation

This is the entry point for reviewing and reproducing the **Step 5E evidence-derived, full-function benchmark**. The benchmark tests run-scoped engineering-function query planning and limited-scope answer validation. It is **not a fault-injection tutorial**. For simulation Start/Stop/Reset and the **Fault-01 bias on XMEAS9** Web UI example, see the [root README](../../README.md#operate-the-simulation-and-faults-from-the-web-ui).

> **Evidence status:** A committed [36-case local benchmark summary](../../reports/tep_nexus_benchmark_full_coverage_summary.json) records **36/36 harness passes** on 2026-11-02. These are *limited-scope pipeline validation outcomes*, not independent historian/provenance ground truth. The earlier [Step 5E checkpoint](../research/tep-nexus/tep-nexus-step5e-full-function-coverage.md) predates this execution and still describes it as pending.

## 1. Benchmark scope

The expanded suite is generated from the **user-selected run's** provisional engineering-function registry. A previously observed registry contained **34 supported functions**; other user-selected runs may not meet that prerequisite. The suite retains seven positive and two negative baseline cases and adds 27 positive cases, yielding **34 positive + 2 negative = 36 cases** when the expected registry is available.

| Case group | Count | Expected behavior |
| --- | ---: | --- |
| Supported engineering functions | 34 | Complete the query with the requested measurement, ten-simulation-minute trend, associated asset and provenance; pass the implemented limited-scope answer checks |
| Unsupported or conflicting function requests | 2 | Reject for the intended validation reason, rather than a service outage or model-formatting error |
| **Total** | **36** | **36 harness passes in the recorded local run** |

The seven baseline positive function families are FI, LI, PI, TI, JI, SC and VC. The two negative baseline cases cover an unsupported function (`FI_999`) and a conflicting function selection (`FI_101` versus `VC_101`). The registry and fixture set are specific to the selected run; the generator must not invent or silently drop function identities.

The historical Fault-02 Q1–Q10 LLM evaluation is **a different experiment**, not part of these 36 cases. Its [original reviewer guide](../e4e_tests/fault02_artifact_evaluation_guide_archived.md) and [evaluation findings](../e4e_tests/fault02_final_evaluation_and_paper_findings.md) remain archived for provenance.

## 2. Recorded benchmark results and latency (2026-11-02)

The repository contains an actual [sanitized full-coverage summary](../../reports/tep_nexus_benchmark_full_coverage_summary.json) generated at **2026-11-02 09:28:09 UTC**, with `scope: operator_local_execution_not_independent_provenance_verification`. The values below are calculated from the 36 recorded `elapsed_seconds` fields, using the linear-interpolated 95th percentile definition implemented in [the audit script](../../scripts/audit_tep_nexus_benchmark.py). These are **observed results from one historical local run**, not a guaranteed outcome for another user-selected run.

| Metric | Recorded result |
| --- | ---: |
| Total distinct cases / executions | 36 / 36 (one repeat) |
| Positive cases passing limited-scope checks | 34 / 34 |
| Negative cases rejected as expected | 2 / 2 |
| Total harness passes / failures | **36 / 0** |
| Mean end-to-end latency per case | **57.791 s** |
| Median end-to-end latency | **58.180 s** |
| 95th-percentile end-to-end latency (linear interpolation) | **69.665 s** |
| Minimum / maximum end-to-end latency | **9.375 / 71.406 s** |
| Total sequential measured case time | **2,080.471 s (34.67 min)** |
| Median positive-case latency | **58.852 s** |
| Median negative-case latency | **9.430 s** |
| Positive cases reporting successful answer repair | **34 / 34** |
| Initial failed answer checks recorded before repair | **107** |

The per-case durations include the planner subprocess and, where applicable, answer repair; the two expected-rejection cases finish much faster and **must not be conflated with successful answer-generation latency**. The archived summary does **not** provide per-stage latency breakdowns, hardware specifications, independent SQL-oracle comparisons, or multiple-trial uncertainty intervals. A 36/36 harness pass rate is **not** a 100% independently verified factual-accuracy claim.

For audit or paper reproduction, run:

```powershell
python scripts\audit_tep_nexus_benchmark.py `
  --summary reports\tep_nexus_benchmark_full_coverage_summary.json `
  --output reports\tep_nexus_benchmark_audit.json
```

This audit recomputes counts and latency statistics from the committed summary; without independently prepared expected and actual historian CSVs, it does **not** verify raw observations against an independent oracle.

## 3. What a reviewer needs

- A checkout of a pinned source commit; record `git rev-parse HEAD`, Python version, operating environment and model identifier. A moving branch name alone is not a reproducible source version.
- Python dependencies and a functioning local query-planner environment, including the model/service configured for `scripts/tep_nexus_ollama_query_planner.py`.
- Run-specific mapping-discovery and temporal-coverage snapshots, plus access to the GraphDB/TimescaleDB evidence needed by the planner. The benchmark generator itself reads local snapshots and **does not connect to GraphDB, TimescaleDB or Ollama**.
- A verified historian run with eligible functions. **The reviewer supplies the run ID** of a run they have actually recorded or restored; a fresh database does not automatically contain historical runs. The benchmark must use the same run ID consistently for fixture generation, mapping discovery, temporal coverage, and execution.

The local paths `reports/tep_nexus_mapping_discovery.json` and `reports/tep_nexus_temporal_coverage.json` must describe the **same user-selected run**. These files are prerequisites, not generated by the commands below. The fixture generator checks for exactly 34 eligible functions by default and fails if baseline positive functions are missing. If the count differs, investigate the underlying snapshots; do not override the check merely to obtain 36 cases.

For local infrastructure startup, use the [root README](../../README.md#local-startup-windows-powershell). Starting services does not restore historical data.

## 4. Generate and run the 36-case benchmark

From the repository root in Windows PowerShell, using a source checkout and local snapshots verified for **your selected run**. Replace the placeholder with an actual historian run ID; do not copy an ID from an unrelated experiment:

```powershell
$runId = "<YOUR_VERIFIED_RUN_ID>"

python scripts\tep_nexus_expand_benchmark.py `
  --run-id $runId `
  --output reports\tep_nexus_benchmark_full_coverage_cases.json
```

Inspect the generated JSON before running it. **Expected, conditional on a valid 34-function registry:** 36 fixtures comprising 34 positive and two negative cases. The generator's output is a constructed test set, **not a benchmark execution result**.

A controlled pilot with a few new supported functions is advisable before the full suite. Run the generated fixtures with the same `$runId`:

```powershell
python scripts\tep_nexus_benchmark.py `
  --fixtures reports\tep_nexus_benchmark_full_coverage_cases.json `
  --run-id $runId `
  --repeats 1 `
  --timeout 300 `
  --summary reports\tep_nexus_benchmark_full_coverage_summary.json
```

The runner writes a sanitized summary to the supplied `--summary` path and per-case planner reports under `reports/tep_nexus_benchmark_runs/` by default. It reports total, passed, failed, per-case classifications, elapsed time, available stage timings, answer-validation status and repair metadata. A nonzero exit code indicates at least one failed case.

The Step 5E checkpoint's **25–35-minute estimate** was a pre-execution forecast. The committed 36-case summary records **34.67 minutes of summed per-case execution time**; actual wall-clock time may differ due to overhead. For repeated trials, specify `--repeats N` and report the resulting total as **36 × N executions**, not N new distinct questions.

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

**Current publication boundary:** The committed summary establishes a recorded **36/36 limited-scope local harness result** with observed end-to-end latencies. It does **not** establish an independently reproducible data bundle, independently verified historian/provenance correctness, or physical-world validation.
