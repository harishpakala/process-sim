# TEP NEXUS — Step 4 multi-function local integration checkpoint

**Evidence date:** 2026-11-02 (operator-supplied local results).  
**Scope:** Offline tests and two local integration executions; not CI or independently rerun services.

## Test results

The operator reported `python -m unittest discover -s tests -p "test_tep_nexus_*.py" -v`: **57 tests, 57 passed**, elapsed 0.048 s.

The two operator-supplied JSON reports recorded:

| Field | FI_101 | VC_101 |
|---|---|---|
| Planner intent | latest_and_history | latest_and_history |
| Signal | XMEAS1 | XMV1 |
| History samples | 201 | 201 |
| Latest simulation time (s) | 3514.0 | 3514.0 |
| Latest value | 0.25016506253200677 | 63.05263039 |
| Mean | 0.2506004258780337 | 63.05263039 |
| Population std. dev. | 0.0012511482919781527 | 0.0 |
| OLS slope / simulation minute | 1.528065315020885e-05 | 0.0 |
| Endpoint change | -0.000503544571995751 | 0.0 |
| Original answer checks passed | 11/14 | 8/14 |
| Final answer checks passed | 14/14 | 14/14 |
| Deterministic repair | succeeded | succeeded |
| Final status | COMPLETED | COMPLETED |
| Final validation | CHECKS_PASSED_LIMITED_SCOPE | CHECKS_PASSED_LIMITED_SCOPE |

The function registry listed 34 supported identifiers in each report. The latest records were stale at query time (FI: 29395.202 s; VC: 29560.341 s). Both results retained provisional mapping and unverified shared-run provenance and physical-binding caveats.

## Interpretation

This is a **successful local multi-function integration checkpoint** spanning FI and VC function families. It supports closing roadmap Step 4 **at checkpoint scope**, not a claim that all 34 identifiers have passed end-to-end tests. In particular, answer validation checks selected numeric claims and caveats only; it does not verify arbitrary free-form claims, physical relationships, or the source systems.

## Next milestone

Step 5: a reproducible benchmark runner using explicit test cases, recorded outcomes, failure classifications, timing, and sanitized summaries. Negative/unsupported queries must be evaluated against an expected rejection rather than counted as execution failures.

**Evidence handling:** The source JSON files were supplied by an operator and are not committed here. Do not commit credentials, DSNs, or unsanitized operational output.
