# Fault-02 E4E manual answer review — Q3, Q5, Q8

Status: **manual review recorded for Q3, Q5, Q8 only**. Other questions remain to be finalized. This is a separately labeled follow-up experiment, not a modification of the frozen November 2026 baseline.

## Provenance

- Repository: `harishpakala/process-sim`, branch `main`
- Simulation run: `a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5`
- Evidence: `reports/tep_nexus_e4e_evidence_fault02.json` (local experiment artifact)
- Original answers: `reports/e4e_comparison/fault02/original/llm_answers.json` (local experiment artifact)
- Revised answers: `reports/e4e_comparison/fault02/revised/llm_answers.json` (local experiment artifact)
- Model: `llama3.1:8b`
- Prompt version: `E4C_V1_EXPLICIT_FIELD_GROUNDING`
- Prompt SHA-256: `d556b0fcc819698af316af8134ec96131f0212fd13b9d5b7eaf67bf371f6a40d`
- Question sets: `docs/e4e_tests/original_questions_fault02.json` and `docs/e4e_tests/revised_questions_fault02.json` (local experiment artifacts; do not assume these are committed)
- Grades below assess actual `ollama_answer` outputs, not the deterministic `reference_answer`. The runner's `NOT_AUTOMATICALLY_VERIFIED` status is not an accuracy grade.

## Agreed decisions

| Question | Original | Revised | Review rationale |
|---|---|---|---|
| Q3 | **PASS** | **PASS** | All four requested canonical AAS asset identifiers and TEP signal references are correct. Both responses include inaccurate ancillary `limitations` claiming product/manufacturer/ECLASS information is unavailable; record this separately as an answer-quality defect. The tested question is vague and context-dependent, but its wording and answers are preserved. |
| Q5 | **PARTIAL** | **PARTIAL** | Original provides the ECLASS/QUDT mapping but does not distinguish catalog/product-family specifications from verified installed-instrument properties and uses imprecise QUDT attribution. Revised explicitly addresses verification status but incompletely covers QUDT provenance for pressure and temperature. ECLASS verification is pending; physical installation is not independently established. |
| Q8 | **FAIL** | **FAIL** | Both identify the recorded `paper-fault-02` injection command at 35.0 simulation seconds, but both assert actual activation/verification without independent evidence. The event is an `operator_command`, not an independently confirmed activation event. Subsequent measurements do not prove activation or causality. |

### Q3 — accepted requested mappings

| DEXPI reference | Canonical AAS AssetIdentifier | TEP signal |
|---|---|---|
| `PI_101` | `https://aas.example.com/PI101` | `XMEAS7` |
| `FI_106` | `https://aas.example.com/FI106` | `XMEAS6` |
| `TI_101` | `https://aas.example.com/TI101` | `XMEAS9` |
| `LI_101` | `https://aas.example.com/LI101` | `XMEAS8` |

For future *newly versioned* question sets, a less ambiguous Q3 could specify DEXPI references, canonical AAS AssetIdentifiers and TEP XMEAS signals. **Do not retroactively change the tested Q3.**

### Q5 — evidence boundaries

Recorded ECLASS classes are pressure `27-27-49-05`, flow `27-20-04-03`, temperature `27-27-51`, and level `27-20-05-05`. The associated product-specification QUDT units/quantity kinds are pressure BAR/Pressure, flow KiloGM-PER-HR/MassFlowRate, temperature DEG_C/Temperature, and level M and MilliM/Length. These mappings are not independent verification of installed physical instruments. The original and revised questions are different; interpret the grades with the actual tested wording in mind.

### Q8 — correct bounded statement

The selected run records event `3ccebd11-1949-4425-86c8-9d5e328147e8`: `fault_id=paper-fault-02`, `action=inject`, `event_source=operator_command`, `simulation_seconds=35.0`. This establishes a **recorded injection command**, not independent confirmation that the requested fault became active. Available adjacent samples are at 34.0 s and 38.0 s, not at 35.0 s, and do not establish causality.

## Evaluation integrity

- The grading rule for Q3 is **task-focused correctness** of requested mappings; ancillary unsupported claims are documented rather than hidden.
- Q5 and Q8 are graded against their substantive evidence/verification requirements; Q8's activation assertion is a central unsupported claim.
- No automatic accuracy score, improvement claim, repeated-run reliability, physical-installation claim, or causal-fault claim follows from these decisions.
- No overall 10-question score is finalized in this file. Preserve the original/revised LLM outputs, frozen baseline and historical question files unchanged.
