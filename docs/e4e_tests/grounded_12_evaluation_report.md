# TEP NEXUS — Grounded Q1–Q12 Evaluation Report

**Status:** Paper-ready draft; qualitative ratings are preliminary and require reviewer sign-off before publication.  
**Evaluation date:** 2026-11-09 (UTC).  
**Repository branch:** `refactor/repository-cleanup`.  
**Source run artifact:** User-provided `answers_12(3).json` (generated `2026-11-09T11:14:49.159952+00:00`); the raw JSON has **not** been archived by this report commit.

## 1. Experimental configuration

| Property | Recorded configuration |
|---|---|
| Simulation run ID | `53b37c4d-b8ba-4e37-8f49-6765a156dc17` |
| Model | Ollama `llama3.1:8b` |
| QA method | `evidence_conditioned_ollama_qa_not_live_vtkg_execution` |
| Question set | Revised independent Q1–Q12 |
| Evidence | Read-only GraphDB-verified cross-domain mappings, AAS AssetInventory/ProductCatalog, and TimescaleDB historian snapshots, as applicable |
| Q12 interval | Inclusive 0–60 simulation seconds |
| Q12 observations | 22; last sample at approximately 59 seconds; no recorded 60-second sample |
| GraphDB verification error | `null` |
| Per-question evidence status | 12/12 `EVIDENCE_AVAILABLE` |
| Per-question runtime errors | None reported |
| JSON assessment status | `NOT_MANUALLY_ASSESSED` |
| Grounding intervention | Explicitly constrain answers to JSON; distinguish logical mappings from physical installation, injection commands from activation, simulation time from observed_at, and floating-point representation from timing discrepancies |

The script `scripts/run_tep_nexus_12.py` generates `reports/evaluation_12_grounded/answers_12.json` locally. The grounded file records the exact grounding instructions and evidence SHA-256 per question. Neither the script nor the JSON performs automated grading. The evaluation does **not** demonstrate live VTKG query execution or VTKG-to-SQL equivalence.

## 2. Evaluation questions and required evidence

| Question | Capability tested | Relevant evidence |
|---|---|---|
| Q1 | Reactor instrument identification | GraphDB-verified AAS engineering mappings |
| Q2 | ECAD device reference retrieval | ECAD local identifiers in verified mappings |
| Q3 | Canonical asset-to-signal alignment | Canonical AAS identifiers and operational signal references |
| Q4 | Product candidate/manufacturer association | AAS AssetInventory and ProductCatalog |
| Q5 | ECLASS and QUDT attribute interpretation | ProductCatalog classification, units, quantity kinds and verification status |
| Q6 | DEXPI–ECAD–AssetInventory reconciliation | GraphDB-verified canonical asset mappings |
| Q7 | PI-1101 multi-domain traceability | DEXPI, ECAD, AssetInventory, ProductCatalog, XMEAS7 |
| Q8 | Fault-command provenance and uncertainty | Recorded `paper-fault-01` injection command |
| Q9 | Observations adjacent to injection command | XMEAS6–XMEAS9 at approximately 27 and 30 simulation seconds |
| Q10 | FI-1101 engineering/temporal integration | Verified asset mappings, ProductCatalog and XMEAS6 historian observations |
| Q11 | Product-candidate ECLASS IRDI lookup | TI-1101 / IFM_TA1101 ProductCatalog evidence |
| Q12 | Temperature historian observation retrieval | TI-1101 / XMEAS9 observations within 0–60 simulation seconds |

## 3. Assessment rubric and question-level results

Use `docs/e4e_tests/qa_manual_assessment_rubric.md` for rating criteria. PASS means all requested material facts are correct without materially misleading unsupported claims; PARTIAL means the core facts are mostly correct but a material unsupported inference, omission or ambiguity remains; FAIL means central requested facts are incorrect or absent. These are **preliminary qualitative ratings made from the supplied answer text**, not automatically generated grades and not an independently adjudicated assessment.

| ID | Preliminary rating | Assessment justification |
|---|---|---|
| Q1 | PASS | Correctly identifies PI-1101/XMEAS7, FI-1101/XMEAS6, TI-1101/XMEAS9 and LI-1101/XMEAS8 as the integrated logical reactor instruments. |
| Q2 | PASS | Correctly reports all four ECAD device identifiers and associates them with the corresponding canonical assets. |
| Q3 | PASS | Correctly reports all four canonical AAS AssetIdentifiers and XMEAS signal mappings; physical-installation caveat is appropriate. |
| Q4 | PASS | Correctly identifies pressure and flow Endress+Hauser candidates, IFM temperature candidate, and Endress+Hauser level candidate. Caveat: the answer generalizes the installation-verification field; TI-1101's source field is null rather than an explicit `NOT_INSTALLED_VERIFIED` value. This does not alter the main product/manufacturer answer. |
| Q5 | PASS | Correctly reports four ECLASS classifications, QUDT units and quantity kinds, and lack of independent physical installation verification. Caveat: `installation_verification` is not uniformly populated as claimed; physical product attributes remain unverified for actual installations. |
| Q6 | PASS | Correctly reports canonical asset URIs and DEXPI/ECAD identifiers for all four instruments; explicitly grounds joins in verified GraphDB mappings. |
| Q7 | PASS | Correct PI-1101 DEXPI, ECAD, AssetInventory, ProductCatalog and XMEAS7 associations; correctly avoids physical-installation claim. |
| Q8 | PASS | Correctly reports `paper-fault-01` operator `inject` command at 30.0 simulation seconds and explicitly states activation is not independently proven. |
| Q9 | PASS | Correctly reports all four signals at ~27 and 30 simulation seconds and explicitly distinguishes recorded injection request from actual activation. The word “After” for the 30-second observation is temporally imprecise; it must not be interpreted as verified post-fault behavior. |
| Q10 | PASS | Correctly reports FI-1101 canonical ID, DEXPI/ECAD identifiers, product candidate, ECLASS classification, XMEAS6, both values and timestamps; preserves activation uncertainty. |
| Q11 | PASS | Correctly reports ECLASS IRDI `0173-1#01-AHB186#005` for the TI-1101-associated IFM product candidate. |
| Q12 | PARTIAL | Correctly reproduces all 22 XMEAS9 samples in the requested interval, but infers that the initial 0.0 value indicates an uninitialized instrument or invalid reading; this interpretation is not supported by the provided historian evidence. |

**Aggregate (preliminary):** evidence available **12/12 (100%)**; full PASS **11/12 (91.7%)**; PARTIAL **1/12 (8.3%)**; FAIL **0/12 (0%)**. These are question-level counts, not retrieval accuracy, statistical confidence intervals, or automatic benchmark scores.

## 4. Q12 partial-result analysis

Q12 requests the recorded temperature-signal observations for reactor temperature instrument TI-1101 (`XMEAS9`) between simulation time 0 and 60 seconds. The read-only TimescaleDB evidence includes 22 observations. The model reproduces all 22 timestamp/value pairs, including the recorded value `0.0` at simulation time `0.0` seconds and the last sample at approximately 59 seconds.

The generated answer adds: “the value at simulation time 0.0 seconds is 0.0, indicating that the instrument was not initialized or was not providing a valid reading at the start of the simulation.” The supplied evidence establishes only that the recorded value is zero; it does **not** establish instrument initialization state, measurement validity, or the cause of the value. Consequently, numerical retrieval and reproduction are correct, but explanatory grounding is imperfect. Q12 is rated PARTIAL, not FAIL, because the requested observations are present and correctly reproduced.

Retain the original generated answer without editing it. Do not silently replace the unsupported statement with a corrected explanation in the archived evaluation output.

## 5. Discussion and limitations

The evaluation demonstrates the ability of an evidence-conditioned language model to answer a fixed, cross-domain question set using supplied engineering and historian evidence. Canonical AAS AssetIdentifiers align DEXPI, ECAD and AssetInventory representations; ProductCatalog records supply product-candidate classifications and attributes; and historian samples supply operational observations. A GraphDB-verified logical mapping does **not** prove physical installation or a final product selection. ProductCatalog QUDT units do **not** automatically establish the units of raw historian measurements. A recorded fault injection command does **not** independently establish that the requested fault activated, nor does temporal proximity prove causation.

The experiment is limited to one 12-question suite, one recorded simulation run, one model configuration, and evidence-conditioned QA. The 91.7% full-pass rate is a descriptive, preliminary qualitative assessment; it should not be generalized to other runs, models, unseen questions, or live VTKG execution. A separate held-out evaluation and independent reviewer adjudication would strengthen external validity.

## 6. Paper-ready results paragraph

> The evidence-conditioned TEP NEXUS evaluation comprised 12 independently formulated questions addressing cross-domain engineering identification and reconciliation, product classification, operational signal mapping, fault-command provenance, and time-series observations. Evidence was available for all 12 questions (100%), with no reported GraphDB verification error. Preliminary qualitative assessment classified 11 answers as PASS (91.7%) and one as PARTIAL (8.3%); none was classified as FAIL. The partial result concerned the TI-1101 temperature-series question: the model reproduced all 22 recorded observations but interpreted an initial zero reading as evidence of an uninitialized or invalid instrument, an inference not supported by the supplied evidence. This distinction illustrates that accurate retrieval and numerical reporting do not eliminate unsupported language-model interpretation. The experiment evaluates evidence-conditioned Ollama QA, not live VTKG query execution.

## 7. Reproducibility and sign-off checklist

- [x] Revised independent questions committed (`docs/e4e_tests/revised_questions.json`; Q11–Q12 are defined in the runner).
- [x] Grounding instructions committed in `scripts/run_tep_nexus_12.py`.
- [x] Manual rubric committed in `docs/e4e_tests/qa_manual_assessment_rubric.md`.
- [x] Source grounded output supplied for review (`answers_12(3).json`).
- [ ] Archive the **unaltered** grounded `answers_12.json` in the repository or a permanent artifact store; record its file-level SHA-256.
- [ ] Obtain human reviewer sign-off for all 12 preliminary ratings, especially the minor caveats in Q4, Q5 and Q9.
- [ ] Record exact repository commit, environment versions, model digest, and source snapshot identifiers for final reproduction.
- [ ] If claiming generalization, evaluate unseen questions or a separate simulation run.

**Integrity note:** This report is an assessment narrative, not a replacement for the original JSON. Its commit does not itself archive the raw evaluation artifact.
