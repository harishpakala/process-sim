# TEP NEXUS — Artifact Evaluation and Reproducibility Guide

This guide accompanies the TEP NEXUS paper's **selected fault02 experiment**. It distinguishes (A) replay of the *same evidence* from (B) generating *new evidence*. **Testing is closed**; these instructions are for independent reviewer assessment, not additional author experiments.

> **Availability warning (checked on `main`, 2026-11-03):** The run-specific `docs/e4e_tests/original_questions_fault02.json` is **not committed**. The final evaluation record references other local files under `reports/` whose availability has **not** been established. Consequently, the archived-evidence replay is **not yet independently executable from a fresh clone**. Authors must deposit the exact question sets, evidence report, and LLM outputs in a permanent artifact bundle and provide hashes/links before claiming turnkey reproduction. Do not substitute historical `paper-fault-01` questions.

## 1. What is being reproduced?

Selected run ID: `a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5`. The selected event is an **operator injection command**, `paper-fault-02`, recorded at 35.0 simulation seconds; it is **not** independently verified fault activation. Four reactor-related signals have adjacent samples at 34.0 and 38.0 seconds. Two sets of ten questions were answered twice each with Ollama `llama3.1:8b` and prompt version `E4C_V1_EXPLICIT_FIELD_GROUNDING` (SHA-256 `d556b0fcc819698af316af8134ec96131f0212fd13b9d5b7eaf67bf371f6a40d`).

The manual task-focused grades are **8 PASS, 1 PARTIAL, 1 FAIL per question set per execution**; the repeated answers matched the earlier answers within each set. See [final evaluation record](../e4e_tests/fault02_final_evaluation_and_paper_findings.md) and [detailed Q3/Q5/Q8 review](../e4e_tests/fault02_manual_review_q3_q5_q8.md).

## 2. Obtain source and record provenance

Use Windows PowerShell from the repository root (other shells require syntax adjustments):

```powershell
git clone https://github.com/harishpakala/process-sim.git
cd process-sim
git rev-parse HEAD
python --version
```

For exact source reproducibility, use the **specific artifact release commit** once published; `main` changes over time. The historical frozen baseline is `3d40b6af97299826fdd1fc30e17c8bca5f8fd0a6` and must remain untouched; the fault02 documentation was added later, so the historical baseline alone is **not** the complete artifact.

## 3. Mode A — replay the original evidence (preferred, after artifact deposit)

Prerequisites: Python, `requests` for the Ollama HTTP calls, a running Ollama service with `llama3.1:8b`, and the archived artifact bundle containing the exact paths below. Install Python requirements appropriate to the repository environment; at minimum, the query script imports `requests` when Ollama is enabled.

```powershell
ollama pull llama3.1:8b
python -m pip install requests
```

Verify that the artifact bundle provides:

```text
reports/tep_nexus_e4e_evidence_fault02.json
docs/e4e_tests/original_questions_fault02.json
docs/e4e_tests/revised_questions_fault02.json
reports/e4e_comparison/fault02/original/llm_answers.json
reports/e4e_comparison/fault02/revised/llm_answers.json
reports/e4e_comparison/fault02/repeat02/original/llm_answers.json
reports/e4e_comparison/fault02/repeat02/revised/llm_answers.json
```

**Do not run the following commands until those inputs are available.** Each command writes a new reviewer-local file rather than overwriting the published results:

```powershell
python scripts/tep_nexus_paper_queries.py `
  --evidence reports/tep_nexus_e4e_evidence_fault02.json `
  --questions docs/e4e_tests/original_questions_fault02.json `
  --ollama-url http://localhost:11434 --model llama3.1:8b `
  --output reports/reviewer_replay/original/llm_answers.json

python scripts/tep_nexus_paper_queries.py `
  --evidence reports/tep_nexus_e4e_evidence_fault02.json `
  --questions docs/e4e_tests/revised_questions_fault02.json `
  --ollama-url http://localhost:11434 --model llama3.1:8b `
  --output reports/reviewer_replay/revised/llm_answers.json
```

Inspect `source_run_id`, `prompt_sha256`, `question_set_sha256`, `answer_generation_mode`, each `ollama_answer`, and each `ollama_error`. The script reports `NOT_AUTOMATICALLY_VERIFIED`; it **does not grade correctness**. Apply the recorded manual task-focused rubric, noting Q3's contradictory ancillary limitations, Q5's product-family provenance problem, and Q8's unsupported activation assertion. Ollama outputs may vary across environments even at temperature zero; compare substantive facts and qualifications, not just exact text.

## 4. Mode B — regenerate evidence from a persisted run (requires services/data)

See [main README local startup](../../README.md#local-startup-windows-powershell) and [semantic setup](../../semantic/README.md). The evidence script is **read-only** and **does not inject faults or start a simulation**. It requires a populated GraphDB SPARQL repository with exact four-domain joins, AAS JSON sources, and a TimescaleDB historian containing the selected run's operator command and signal samples. Merely starting the services is insufficient.

```powershell
$env:TEP_TIMESCALE_DSN = "postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus"
python scripts/tep_nexus_paper_evaluation.py `
  --graphdb-url http://localhost:7200/repositories/AAS `
  --run-id a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5 `
  --output reports/reviewer_replay/evidence_from_historian.json
```

This command needs the **original run records** in the configured database. A fresh database will not contain the selected run. The DSN shown is a local-development example, not a production credential. For a newly created run, supply its *actual* run ID and archive its own evidence separately; do not claim that its measurements must match the published run.

To check the available CLI arguments:

```powershell
python scripts/tep_nexus_paper_evaluation.py --help
python scripts/tep_nexus_paper_queries.py --help
```

GraphDB exact-join verification must succeed for relevant cross-domain questions. `evidence-available 10/10` is an evidence-presence result, not proof of LLM answer correctness or physical installation. This guide does not assert that a complete clean-machine GraphDB/TimescaleDB bootstrap or operator fault command sequence has been independently verified.

## 5. Expected selected-run observations

| Signal | 34.0 s | 38.0 s |
| --- | ---: | ---: |
| XMEAS6 | 42.484025175435605 | 42.07586204745709 |
| XMEAS7 | 2704.903453038064 | 2704.99975408382 |
| XMEAS8 | 74.41177807996309 | 74.97420993656078 |
| XMEAS9 | 120.41150921909319 | 125.39120858001397 |

There is no recorded sample exactly at 35.0 s in the selected evidence. Neither these differences nor the operator command verify fault activation or causal effect.

## 6. Reviewer checklist and remaining packaging obligations

- Confirm source commit, Python/Ollama versions, model identity, prompt hash, and exact question/evidence file hashes.
- Confirm Q1–Q10 evidence statuses independently of natural-language grading.
- Inspect the `ollama_answer` field, **not** the deterministic `reference_answer`, when grading the LLM.
- Use the manual rubric in the final evaluation record; retain all partial/failed cases.
- Archive the missing run-specific inputs and four original outputs in a versioned release with SHA-256 manifest.
- Document the tested GraphDB loading procedure and the historian/run export or fixture needed for Mode B before claiming fully automated end-to-end reproducibility.

**Evidence boundaries:** logical simulation mappings are not verified physical installation; ECLASS release verification remains pending; operator commands are not confirmed fault activations; two executions on one evidence snapshot do not demonstrate independent-run robustness.
