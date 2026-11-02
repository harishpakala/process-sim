# Two-function reasoning prototype — local verification

**Status:** implementation committed; offline and live verification pending.

This is a deliberately isolated prototype. The existing single-function pipeline and benchmark are unchanged. It tests LLM interpretation and cross-source synthesis, not simulator or controller performance.

## Run offline tests (PowerShell)

```powershell
git pull --ff-only
python -m unittest discover -s tests -p "test_tep_nexus_two_function_reasoning.py" -v
```

Expected: nine new tests. No local result is claimed until executed.

## Run one live research question

Requires local Ollama, GraphDB, TimescaleDB, the existing mapping-discovery and temporal-coverage JSON snapshots, and TEP_TIMESCALE_DSN.

```powershell
python scripts\tep_nexus_two_function_reasoning.py `
  --question "Compare FI_101 and PI_101 over the last 10 simulation minutes. Which changed more relative to its initial value?" `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --output reports\tep_nexus_two_function_comparison.json
```

Inspect `status`, `raw_plan`, `validated_plan`, `evidence.mappings`, `evidence.comparison`, `llm_answer`, and `llm_answer_validation`.

**Interpretation:** `COMPLETED_UNVERIFIED_NARRATIVE` means the two source retrievals and deterministic comparison succeeded; it does **not** mean the LLM explanation was checked for numeric correctness or completeness. The next research milestone is an independent answer checker for this comparison, plus source-attribution scoring.

**Method limitations:** series are compared only at exactly matching simulation-second timestamps, without interpolation. A shared simulation interval does not verify shared physical provenance. Truncated histories, insufficient shared samples and missing series fail closed. A zero baseline makes relative percentage change unavailable. Comparison of unlike signal units uses relative percentage change only; it is descriptive, not causal or physically equivalent.

**Evidence limitations:** mappings are provisional; sensor binding and common run provenance remain unverified. No controller-causality claim is justified.
