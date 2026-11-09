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

## 2. The 36 benchmark questions

The table below reproduces the **exact question text and case order** from the [committed benchmark test cases](../../reports/tep_nexus_benchmark_full_coverage_cases.json) (also available as a [test fixture copy](../../tests/fixtures/tep_nexus_full_36_cases.json)). These are the questions from the recorded local benchmark; generating cases for another run depends on its supported-function registry.

| # | Engineering function | Question | Expected outcome |
| ---: | --- | --- | --- |
| 1 | `FI_101` | For engineering function FI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 2 | `VC_101` | For engineering function VC_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 3 | `TI_101` | For engineering function TI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 4 | `LI_101` | For engineering function LI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 5 | `PI_101` | For engineering function PI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 6 | `JI_101` | For engineering function JI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 7 | `SC_101` | For engineering function SC_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 8 | `FI_999` | Show the latest measurement for engineering function FI_999. | Reject |
| 9 | `FI_101` | Show the latest measurement for FI_101 and VC_101. | Reject |
| 10 | `FI_102` | For engineering function FI_102, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 11 | `FI_103` | For engineering function FI_103, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 12 | `FI_104` | For engineering function FI_104, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 13 | `FI_105` | For engineering function FI_105, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 14 | `FI_106` | For engineering function FI_106, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 15 | `FI_107` | For engineering function FI_107, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 16 | `FI_108` | For engineering function FI_108, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 17 | `FI_109` | For engineering function FI_109, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 18 | `FI_110` | For engineering function FI_110, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 19 | `LI_102` | For engineering function LI_102, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 20 | `LI_103` | For engineering function LI_103, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 21 | `PI_102` | For engineering function PI_102, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 22 | `PI_103` | For engineering function PI_103, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 23 | `TI_102` | For engineering function TI_102, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 24 | `TI_103` | For engineering function TI_103, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 25 | `TI_104` | For engineering function TI_104, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 26 | `TI_105` | For engineering function TI_105, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 27 | `VC_102` | For engineering function VC_102, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 28 | `VC_103` | For engineering function VC_103, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 29 | `VC_104` | For engineering function VC_104, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 30 | `VC_105` | For engineering function VC_105, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 31 | `VC_106` | For engineering function VC_106, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 32 | `VC_107` | For engineering function VC_107, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 33 | `VC_108` | For engineering function VC_108, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 34 | `VC_109` | For engineering function VC_109, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 35 | `VC_110` | For engineering function VC_110, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |
| 36 | `VC_111` | For engineering function VC_111, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance. | Complete |

The two rejection cases intentionally test unsupported and conflicting function identifiers; a correct rejection counts as a harness pass.

## 3. Recorded benchmark results and latency (2026-11-02)

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

## 4. Generate and run the 36-case benchmark

From the repository root in Windows PowerShell, with Python dependencies, a working query-planner/model service, and access to the required GraphDB/TimescaleDB evidence. The existing `reports/tep_nexus_mapping_discovery.json` and `reports/tep_nexus_temporal_coverage.json` snapshots must both correspond to **your selected, verified historian run**; the commands below do not generate these snapshots or restore historical data. The generator requires 34 eligible functions by default. See the [root README](../../README.md#local-startup-windows-powershell) for local service startup.

Replace the placeholder with your actual run ID, not an ID copied from another experiment:

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

**Current publication boundary:** The committed summary establishes a recorded **36/36 limited-scope local harness result** with observed end-to-end latencies. It does **not** establish an independently reproducible data bundle, independently verified historian/provenance correctness, or physical-world validation.
