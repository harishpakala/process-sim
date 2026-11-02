# Two-function LLM answer validation — research checkpoint

The comparison prototype now scores **the original LLM explanation**, without deterministic repair. It retains the existing evidence and records `llm_answer_validation` and `llm_answer_validation_details`. The checker verifies explicit source/number coverage and limited unsupported-causality wording; it is **not** a full semantic or hallucination detector.

## Local tests (PowerShell)

```powershell
git pull --ff-only
python -m unittest discover -s tests -p "test_tep_nexus_comparison_answer_validation.py" -v
python -m unittest discover -s tests -p "test_tep_nexus_two_function_reasoning.py" -v
```

## Re-run the research question

```powershell
python scripts\tep_nexus_two_function_reasoning.py `
  --question "Compare FI_101 and PI_101 over the last 10 simulation minutes. Which changed more relative to its initial value?" `
  --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b `
  --output reports\tep_nexus_two_function_comparison_validated.json
```

Upload the JSON report. Interpret `COMPLETED_WITH_ANSWER_CHECK_FAILURES` as a valid and informative research outcome, not a failed data-integration experiment.

## Interpretation cautions

- The comparison uses exact shared simulation timestamps, not interpolation.
- Percentage values are matched within an explicit formatting tolerance; a matching number elsewhere in the narrative can be falsely accepted. Winner recognition is phrase-limited and can falsely reject valid paraphrases.
- The checker does not verify every assertion in the response or the semantics of GraphDB relationships.
- Keep raw LLM accuracy distinct from any future deterministic answer repair.
- Mapping, physical binding and shared-run provenance limitations remain unchanged.
