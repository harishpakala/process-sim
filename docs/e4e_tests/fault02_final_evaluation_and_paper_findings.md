# TEP NEXUS — final fault02 evaluation record and manuscript-ready findings

**Evaluation closed:** 2026-11-03. No further testing is required for this reported evaluation. This record does not modify the frozen November 2026 baseline.

## Experimental scope and provenance

- Simulation run: `a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5`.
- Selected event: `paper-fault-02`, `action=inject`, `event_source=operator_command`, `simulation_seconds=35.0`, event ID `3ccebd11-1949-4425-86c8-9d5e328147e8`.
- Adjacent samples: simulation times 34.0 s (before) and 38.0 s (after); **no measurement at exactly 35.0 s in the selected evidence**.
- Evidence report: `reports/tep_nexus_e4e_evidence_fault02.json` (locally generated; may not be tracked in Git).
- Question sets: `docs/e4e_tests/original_questions_fault02.json` and `docs/e4e_tests/revised_questions_fault02.json` (local experiment inputs; may not be tracked in Git).
- Outputs: `reports/e4e_comparison/fault02/{original,revised}/llm_answers.json` and `reports/e4e_comparison/fault02/repeat02/{original,revised}/llm_answers.json` (local artifacts; may not be tracked in Git).
- Model: `llama3.1:8b`; prompt version `E4C_V1_EXPLICIT_FIELD_GROUNDING`; prompt SHA-256 `d556b0fcc819698af316af8134ec96131f0212fd13b9d5b7eaf67bf371f6a40d`.
- Two executions per question set on **the same evidence**. A direct comparison of the four uploaded JSON files confirmed that the `ollama_answer` objects for all ten question IDs were identical between executions within each set. This does not establish independent-run reliability.
- The runner reports `NOT_AUTOMATICALLY_VERIFIED`; grades below are manually assessed and do not originate from the runner.

## Final task-focused grades

| Question | Original | Revised | Basis |
|---|---|---|---|
| Q1 | PASS | PASS | Reactor logical instrument references correctly retrieved |
| Q2 | PASS | PASS | ECAD references correctly retrieved |
| Q3 | PASS | PASS | Four requested AAS IDs and XMEAS mappings correct; contradictory ancillary limitations documented |
| Q4 | PASS | PASS | Linked product/manufacturer associations correctly retrieved within simulation-scope limits |
| Q5 | PARTIAL | PARTIAL | Original omits verification distinctions and conflates catalog values with QUDT annotations; revised improves qualification but incompletely covers pressure and temperature QUDT provenance |
| Q6 | PASS | PASS | Cross-representation AAS identifiers correctly retrieved |
| Q7 | PASS | PASS | PI-1101 engineering mapping correctly retrieved |
| Q8 | FAIL | FAIL | Both answers incorrectly assert verified fault activation from a recorded injection command |
| Q9 | PASS | PASS | XMEAS6–9 before/after values and 34/38 s timestamps correctly reported |
| Q10 | PASS | PASS | FI-1101 canonical mapping and XMEAS6 before/after values correctly reported |

**Distribution:** 8 PASS, 1 PARTIAL, 1 FAIL per question set, per execution. The same distribution recurred in the repeated execution on unchanged evidence. These are descriptive counts for ten questions, not statistical accuracy or reliability estimates. Original and revised Q5/Q8 questions are not semantically identical, so counts alone do not isolate the effect of wording.

## Measurement evidence

| Signal | 34.0 s | 38.0 s |
|---|---:|---:|
| XMEAS6 | 42.484025175435605 | 42.07586204745709 |
| XMEAS7 | 2704.903453038064 | 2704.99975408382 |
| XMEAS8 | 74.41177807996309 | 74.97420993656078 |
| XMEAS9 | 120.41150921909319 | 125.39120858001397 |

## Manuscript-ready evaluation paragraph (draft; integrate with the manuscript's terminology and citations)

We evaluated TEP NEXUS on ten contextualized engineering and operational retrieval questions using a selected Tennessee Eastman Process simulation run. Both the original and revised question sets were answered by `llama3.1:8b` using the same retrieved evidence and fixed prompt version, and each question set was executed twice. Under a manually applied task-focused rubric, each execution yielded eight PASS, one PARTIAL, and one FAIL judgments. All ten `ollama_answer` objects were identical between the two executions within each question set. The system correctly retrieved the evaluated logical engineering identifiers and the recorded XMEAS6–XMEAS9 measurements at 34 and 38 simulation seconds surrounding an operator injection command at 35 seconds. However, answers to the product-classification question did not fully distinguish catalog or product-family attributes from independently verified installed-instrument properties. More critically, both formulations of the fault question elicited unsupported claims that the requested fault had become active, although the available record established only that an operator injection command was issued. These findings demonstrate successful evidence retrieval for the selected logical mappings and temporal samples, alongside a limitation in evidence-boundary interpretation. The repeated executions share the same evidence snapshot and therefore do not establish robustness across independent simulation runs, physical installation, or fault causality.

## Reporting restrictions

Do not claim: verified fault activation, causal response to injection, verified physical instrument installation, confirmed ECLASS release, independent-run reliability, statistical significance, or that evidence availability equals LLM correctness. Do not overwrite the frozen baseline, earlier evaluation outputs, or question-set history.

This record closes the testing phase and is intended to support manuscript completion. Related detailed Q3/Q5/Q8 review: `docs/e4e_tests/fault02_manual_review_q3_q5_q8.md`.
