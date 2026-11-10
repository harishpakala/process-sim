# TEP NEXUS — benchmark and artifact evaluation

This guide documents the original **36-case engineering-function benchmark** and the subsequent **three-arm comparative experiment**. The two evaluations must not be conflated: the historical single-arm measurements in Section 3 are committed results from 2026-11-02, whereas Section 6 describes the later deterministic, hybrid, and full-LLM comparison. Both evaluate a bounded, simulation-based retrieval prototype, not independently verified physical instrumentation.

The existing 36 question texts, recorded historical results, and reproduction instructions are retained below.

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

## 6. Three-arm comparative experiment

The later comparison uses the same **36-case fixture** (34 positive cases and two expected rejections) under three execution strategies. Each case is repeated three times for each strategy: **36 × 3 × 3 = 324 executions**. The harness rotates arm order and records individual case outcomes, stage timings when available, and paired comparisons.

| Arm | Input and execution path | Interpretation |
| --- | --- | --- |
| Deterministic | Structured fixture parameters; validated GraphDB/TimescaleDB retrieval; deterministic evidence-only answer | Low-latency reference **without natural-language interpretation** |
| Hybrid | Ollama-assisted natural-language planning; constrained retrieval; deterministic evidence-only answer | Tests the cost of natural-language planning while avoiding generative answering |
| Full LLM | Ollama-assisted planning and answer generation; application validation and deterministic repair where necessary | Tests full generative-answer pipeline plus checking and repair |

The deterministic and language-model arms **do not receive equivalent input representations**. Consequently, latency differences must not be described as a head-to-head comparison of equal natural-language capabilities. All three strategies use the same fixture expectations for final pipeline checks. An expected rejection counts as success only when the intended validation reason is observed.

### 6.1 Recorded comparative results (local execution)

The following are reported local results of the three-arm experiment, **now archived as case-level JSON and paired CSV in this feature branch**. The archived JSON contains 324 case records and matched triples; the audit script below independently recomputes the reported statistics from those records.

| Metric | Deterministic | Hybrid | Full LLM |
| --- | ---: | ---: | ---: |
| Positive executions passing final checks | 102/102 | 102/102 | 102/102 |
| Expected negative rejections | 6/6 | 6/6 | 6/6 |
| Positive median latency (s) | 0.390 | 8.067 | 42.136 |
| Positive p95 latency (s) | 0.638 | 11.373 | 69.846 |
| Negative median latency (s) | 0.00005 | 7.112 | 7.093 |

Among **102 matched positive executions** (34 distinct positive fixtures, each repeated three times), the median paired full-LLM-minus-hybrid latency difference was **33.953 s**. The **median of individual paired full-LLM/hybrid latency ratios** was **5.31×**; this is not the ratio of the two overall medians.

All **102 initial full-LLM positive answers** failed at least one configured validation check, with **355 failed checks in aggregate**. Each was subsequently reconstructed deterministically and passed the implemented limited-scope final checks. The 355 count refers to failed **checks**, not independent erroneous answers. The hybrid arm's deterministic response construction avoids free-form answer-generation checks by design; that is not evidence of unrestricted language-model answer accuracy.

These measurements include application and local model execution overhead. They should not be generalized across hardware, different model configurations, changed historian contents, or different engineering-function registries.

### 6.2 Run the comparative experiment (Windows PowerShell)

Follow the [root startup guide](../../README.md#local-startup-windows-powershell) to configure GraphDB, TimescaleDB, and Ollama. Prepare a **verified, locally accessible historian run** and ensure the following two existing snapshots describe the **same** run and function registry:

- `reports/tep_nexus_mapping_discovery.json`
- `reports/tep_nexus_temporal_coverage.json`

The repository does **not** restore the historical historian state automatically. Never reuse a run ID from the paper unless its underlying data actually exist in your local database. The default `llama3.1:8b` model must be available through Ollama.

From the repository root:

```powershell
$runId = "<YOUR_VERIFIED_RUN_ID>"
$env:TEP_TIMESCALE_DSN = "<YOUR_LOCAL_TIMESCALE_DSN>"

ollama pull llama3.1:8b

python scripts/tep_nexus_three_arm_experiment.py `
  --run-id $runId `
  --fixtures tests/fixtures/tep_nexus_full_36_cases.json `
  --repeats 3 `
  --model llama3.1:8b `
  --timeout 300 `
  --output reports/tep_nexus_three_arm_experiment.json `
  --csv reports/tep_nexus_three_arm_experiment.csv
```

The runner also writes individual reports to `reports/tep_nexus_three_arm_runs/` by default, checkpoints progress after completed cases, and offers `--resume` to continue a compatible interrupted run. Check the results and exit status before citing a successful trial; merely completing a process does not establish expected negative rejection behavior or observational correctness.

A standalone deterministic baseline and a paired deterministic-versus-LLM experiment are also available:

- [Deterministic baseline instructions](deterministic-baseline.md) and [script](../../scripts/tep_nexus_deterministic_baseline.py).
- [Paired experiment script](../../scripts/tep_nexus_paired_experiment.py). This is a **two-arm** experiment, distinct from the three-arm runner.
- [VTKG-versus-direct comparison script](../../scripts/tep_nexus_baseline_comparison.py), which evaluates a different comparison. The three-arm run does not establish a performance advantage of VTKG over direct data composition.

### 6.3 Audit and statistical reporting

For research reporting, preserve the **raw case-level JSON** in addition to CSV summaries and record the exact Git commit, run ID, fixture checksum, local model configuration, hardware, software versions, and GraphDB/TimescaleDB state. Avoid publishing raw operational data or internal addresses without reviewing them.

For the 102 positive matched triples, pair cases by **fixture ID and repeat number** before computing latency differences and ratios. Because the three repetitions arise from only **34 distinct positive fixtures**, uncertainty intervals should resample fixtures as clusters (retaining their repetitions), rather than assuming 102 independent scenarios. Using 10,000 fixture-clustered bootstrap resamples (seed 20261110), the descriptive 95% interval for the median paired latency difference is **[32.317, 35.420] s**, and for the median paired latency ratio is **[5.076, 5.473]×**. The detailed breakdown of failed validation checks by actual check identifier remains **unavailable in the archived aggregate case records**; do not infer categories from the 355-check total.

Recalculate all arm statistics, paired effects, failed-check totals, and the fixture-clustered intervals with the [three-arm audit script](../../scripts/audit_tep_nexus_three_arm.py):

```powershell
python scripts/audit_tep_nexus_three_arm.py `
  --input reports/tep_nexus_three_arm_experiment.json `
  --output reports/tep_nexus_three_arm_audit.json `
  --iterations 10000 `
  --seed 20261110
```

The original [36-case audit script](../../scripts/audit_tep_nexus_benchmark.py) is for the archived historical benchmark summary; it is **not** a three-arm statistical audit script.

## 7. Engineering traceability worked example

A source-level audit of the reactor-temperature chain is available in the [engineering traceability report](engineering-traceability-reactor-temperature.md). It reconciles DEXPI `TI_101`, ECAD `TI-1101`, AssetInventory `TEP_XMEAS9`, two unresolved EBOM engineering-object entries, the product-catalog candidate, and the provisional `XMEAS9` OPC UA mapping. **This is a documented model-level correspondence, not a completed live RDF traversal or verified installed-device chain.**

The committed temporal coverage snapshot uses a different historian run ID from the archived three-arm experiment; its 1,201 reported samples must not be presented as independent evidence for that three-arm run. See the traceability report for required verification steps.

## 8. Artifact inventory and reproducibility boundary

| Artifact | Status in this feature branch |
| --- | --- |
| Historical 36-case questions and fixture | Committed: [36-case fixture](../../tests/fixtures/tep_nexus_full_36_cases.json) |
| Historical 36-case measurements | Committed: [summary](../../reports/tep_nexus_benchmark_full_coverage_summary.json) |
| Historical summary audit | Committed: [audit script](../../scripts/audit_tep_nexus_benchmark.py) |
| Three-arm runner and the baseline scripts | Committed: [three-arm runner](../../scripts/tep_nexus_three_arm_experiment.py), [hybrid](../../scripts/tep_nexus_hybrid_baseline.py), [deterministic](../../scripts/tep_nexus_deterministic_baseline.py) |
| Run-specific mapping and coverage snapshots | Example/local snapshots exist, but must be checked against the selected historian run |
| Raw three-arm JSON/CSV | Committed: [324 case records and triples](../../reports/tep_nexus_three_arm_experiment.json) and [paired latency CSV](../../reports/tep_nexus_three_arm_experiment.csv) |
| Per-case detailed model-answer validation reports | **Not archived**; aggregate case records provide counts but not individual failed-check identifiers |
| Three-arm statistical audit | Committed: [audit script](../../scripts/audit_tep_nexus_three_arm.py) |
| Restorable historical TimescaleDB/GraphDB experiment state | **Not established as a complete archived dataset** |
| Fixture-clustered uncertainty analysis | Documented and recomputable using the archived JSON and audit script |
| Exact hardware/environment and restorable database state | **Not yet documented as a complete reproduction package** |

A fresh clone can inspect the benchmark code, questions, and committed historical summary. It **can independently recalculate the recorded three-arm summary statistics and fixture-clustered intervals** from the archived JSON, but **cannot independently rerun the recorded experiment** without the corresponding live historian data, semantic state, and model/environment configuration. A fresh local experiment is possible only after those prerequisites are prepared.

The 12 qualitative engineering questions, eight SQL consistency comparisons, and selected negative/virtual-graph tests in the paper are **separate evaluation components**; they should not be counted as additional fixtures or repetitions in the 324-execution comparison.

**Scientific interpretation:** Final harness success indicates consistency with the **implemented limited-scope checks**, not verified sensor installation, fault causality, general LLM factual accuracy, or independent validation of the engineering-to-signal mappings.

## Qualitative Q13 — cross-model traceability (v1 evaluated; v2 pending)

This **adds a proposed thirteenth question to the separate 12-question qualitative engineering evaluation**. It does **not** modify the historical 36-case benchmark, its fixtures, or its reported results. The existing 12-question results (11 PASS, Q12 PARTIAL) remain historical evidence; Q13-v1 was executed locally and its answer was assessed as incomplete; the uploaded local result is not committed to this repository. Q13-v2 is a separate follow-up evaluation with no recorded outcome yet.

**Q13 — Reactor-temperature end-to-end traceability**

> Trace the reactor-temperature measurement across DEXPI, ECAD, Engineering BOM, AssetInventory, ProductCatalog, and OPC UA Connectivity. Identify the shared AssetIdentifier, source engineering tags, BOM item IDs, logical asset, product candidate, and operational signal. Then retrieve XMEAS9 observations for simulation run `10cfb1d1-2984-4932-8207-dc430ed60c2b` over simulation seconds 0–600. Provide evidence for each relationship and explicitly report unresolved or provisional mappings.

**Expected source-level anchors (not a predetermined system answer):** DEXPI `TI_101`; ECAD `TI-1101`; EBOM `EBOM-0016` and `EBOM-0050`; canonical `AssetIdentifier=https://aas.example.com/TI101`; AssetInventory `TEP_XMEAS9`; ProductCatalog candidate `IFM_TA1101`; provisional OPC UA mapping `TI_101 → XMEAS9`. Preserve the distinct ECAD SMC part reference and IFM candidate rather than asserting product equivalence. The specified run is drawn from the archived temporal coverage snapshot; its presence and observations in the live historian must be checked.

**Evaluation:** PASS only if all six model contributions are evidenced by actual returned records/graph statements and the temporal rows are confirmed to belong to the requested run and interval. PARTIAL if links or observations are missing and the system accurately reports those gaps. FAIL if it invents links, conflates candidate products, or returns observations from a different run. Record the actual response, query timestamp, GraphDB evidence, TimescaleDB rows, and verdict before including Q13 in quantitative claims. The updated EBOM JSON must be re-lifted before a live graph test.


### Running Q1–Q12 unchanged with Q13-v2 in the evidence-conditioned Ollama runner

The original Q1–Q12 question texts are unchanged: Q1–Q10 load from
`docs/e4e_tests/revised_questions.json`; Q11 and Q12 remain defined in
`scripts/run_tep_nexus_12.py`. Q13-v2 is appended after Q12, with its own
read-only GraphDB SPARQL and TimescaleDB historian evidence. The script name
is retained to avoid breaking existing references.

From the repository root, with GraphDB, TimescaleDB and Ollama available,
and `TEP_TIMESCALE_DSN` configured **locally** (do not commit credentials):

```powershell
$env:TEP_TIMESCALE_DSN = "postgresql://USER:PASSWORD@localhost:5432/DBNAME"
python scripts/run_tep_nexus_12.py --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b --graphdb-url http://localhost:7200/repositories/AAS --model llama3.1:8b --output-dir reports/evaluation_13_v2_grounded
```

Replace the DSN placeholder with the actual local connection information.
The command runs Q1–Q12 with their pre-existing evidence logic (Q12 uses the
default 0–60-second interval) and adds Q13 with its specified run ID and
0–600-second interval, regardless of the Q12 window arguments. The selected
`--run-id` applies to the existing run-dependent questions.

The runner writes `reports/evaluation_13_v2_grounded/answers_13_v2.json` with
question texts, Ollama responses, evidence hashes and Q13 evidence, plus
`reports/evaluation_13_v2_grounded/evidence/revised/evidence_and_assessment_template.json`
for the existing Q1–Q10 evidence assessment. Q13 SPARQL results include
canonical asset identifiers, product/signal references and OPC UA mapping
provenance. Q13 historian evidence includes XMEAS9 observation values,
simulation times and recorded timestamps. Failed GraphDB queries or missing
historian observations are reported as incomplete evidence rather than
silently asserted.

**Interpretation:** This is evidence-conditioned Ollama QA, **not** a live
VTKG planner execution or automatic PASS/PARTIAL/FAIL grading. Q13's
`EVIDENCE_AVAILABLE` flag is a preliminary data-presence check, not proof
that every relationship is correct. Inspect the actual response and evidence,
preserve provisional mapping and product-selection caveats, and assign
manual grades. Historical Q1–Q12 grades and 36-case benchmark results are
not overwritten. The runner cannot execute against the user's local services
from GitHub alone.

### Q13 question versioning and evidence presentation

**Q13-v1** is the original paragraph quoted above. Its initial local
`answers_13.json` result should be retained unchanged as a failed/incomplete
answer-completeness trial. Do not relabel that run as a PASS.

**Q13-v2** retains the same six-model and 0–600-second historian requirements
but explicitly numbers the seven answer sections and asks for the historian
count and first/last observations rather than all 207 samples. The runner
feeds the model a compact SPARQL triple digest and historian summary for Q13
only. The **full original SPARQL results and all returned historian samples**
remain in the top-level `q13_evidence` output field for audit. Q1–Q12
question text, prompts and evidence logic are not changed.

This revision is an **intervention**, not a directly comparable rerun of the
same question. Report Q13-v1 and Q13-v2 separately, with their question
wording, evidence presentation, model configuration and manual assessments.
A complete answer is not guaranteed: some source tags may not be present in
the current SPARQL evidence, and the model must report such gaps rather than
invent them. The runner still does not perform live VTKG execution or
automatic grading.

### Fast Q13-v2-only rerun

To avoid running Q1–Q12 or their evidence retrieval, add `--only-q13`:

```powershell
python scripts/run_tep_nexus_12.py --only-q13 --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b --graphdb-url http://localhost:7200/repositories/AAS --model llama3.1:8b --output-dir reports/evaluation_13_v2_only
```

This invokes Ollama **once** for Q13-v2, performs only the Q13 GraphDB and
TimescaleDB retrieval, and writes
`reports/evaluation_13_v2_only/answers_q13_v2_only.json`.
It does not create the Q1–Q10 assessment template or invoke the Q1–Q12
retrieval/answer paths. `TEP_TIMESCALE_DSN` must still be set locally.
The result remains ungraded until its answer and evidence are reviewed.
