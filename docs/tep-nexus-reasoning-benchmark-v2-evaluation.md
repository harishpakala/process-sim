# TEP NEXUS benchmark V2 — evaluation protocol

## Purpose
Ten independently prompted questions use one shared live evidence snapshot. Complexity progresses from semantic lookup to cross-domain interpretation. V1 is preserved in its original output JSON; V2 defaults to `reports/tep_nexus_reasoning_benchmark_10_v2.json`.

## Scope and constraints
- GraphDB mapping: FI_101→XMEAS1 and PI_101→XMEAS7, status provisional. No verified physical sensor binding.
- TimescaleDB comparison: intersection of common simulation timestamps, no interpolation. This **does not** assert the original raw timestamp sets were identical.
- Signed percentage is `100 * (last - first) / abs(first)` for nonzero first values; absolute magnitude is `abs(signed_percentage)`.
- The operator-supplied run ID is not independent verification of shared physical provenance.
- Endpoint changes and regression slopes alone cannot establish causal influence, signal independence, or whole-series similarity.
- NOT_VERIFIED means missing verification; it does not mean a claim is contradicted.

## Expected numerical anchors for the current reference snapshot
- FI_101 / XMEAS1: -0.20088058804540695% signed; magnitude 0.20088058804540695%.
- PI_101 / XMEAS7: +0.010290357685705524% signed; magnitude 0.010290357685705524%.
- Greater signed: PI_101. Greater magnitude: FI_101.
- Common aligned samples: 201; simulation seconds 2916–3514; exact common timestamps, no interpolation.
These are **reference-snapshot expectations**, not universal answers for other run IDs or changed data.

## Review rubric (apply per question)
Record separate outcomes:
1. **Question validity:** CLEAR / AMBIGUOUS / INSUFFICIENT_EVIDENCE. Do not grade model accuracy when ambiguous.
2. **Factual correctness:** CORRECT / INCORRECT / INDETERMINATE. Compare against the evidence actually supplied to that question.
3. **Completeness:** COMPLETE / INCOMPLETE. Check every required field or subtask.
4. **Grounding:** SUPPORTED / UNSUPPORTED / MIXED. An absence of evidence cannot establish nonexistence.
5. **Uncertainty calibration:** APPROPRIATE / OVERCLAIM / UNDERCLAIM.
6. **Format:** existing automatic basic format check only; do not treat it as factual success.

For Level 9, H1/H2/H3 are all UNDETERMINED on the available summary: independent variation is not proven, causality is not established or refuted, and provisional mapping is not proof of incorrect attribution. For Level 10, check all six requested parts.

## Interpretation
This benchmark measures interpretation of precomputed multi-source evidence. It does **not** independently measure tool selection, source discovery, full raw-series analysis, or causal identification. Report results per question; do not interpret ten related questions from one snapshot as a general success rate.

## Run
```powershell
python -m unittest discover -s tests -p "test_tep_nexus_reasoning_benchmark_10.py" -v
python scripts\tep_nexus_reasoning_benchmark_10.py --run-id 10cfb1d1-2984-4932-8207-dc430ed60c2b --model llama3.1:8b
```
Review `reports/tep_nexus_reasoning_benchmark_10_v2.json` with the rubric above. The runner currently provides only format checks; manual or separately implemented semantic evaluation is required.
