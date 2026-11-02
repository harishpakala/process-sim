# TEP NEXUS — Quantitative temporal analytics validation

**Local execution:** 2026-11-02T06:13:26.025380+00:00 (timestamp from operator-supplied report)  
**Model:** `llama3.1:8b`  
**Test evidence:** Operator-provided PowerShell console output and `tep_nexus_ollama_planned_query(2).json`.  
**Scope:** One TI_101 / XMEAS9 run; operator-supplied run ID.

## Offline regression testing

- `python -m unittest discover -s tests -p "test_tep_nexus_temporal_analytics.py" -v`: **10 passed, 0 failed** (0.009 s).
- `python -m unittest discover -s tests -p "test_tep_nexus_query_planner.py" -v`: **12 passed, 0 failed** (0.005 s).
- Combined: **22 of 22 tests passed**, operator-reported local execution. This is not an independently observed CI run.

## End-to-end integration result

The constrained Ollama planner generated an accepted `latest_and_history` plan for `TI_101` with a 10-simulation-minute window and asset/provenance requested. The pipeline returned `status: COMPLETED` and `answer_validation: NOT_AUTOMATICALLY_VERIFIED`.

- GraphDB-resolved operational signal: `XMEAS9`; mapping `PROVISIONAL_ENGINEERING_MATCH`.
- TimescaleDB history: **201 observations**, **not truncated**, elapsed **9.966666666666667 simulation minutes**.
- Latest persisted observation: simulation time **3514.0 seconds**, value **120.38819508324035**.
- Latest record age at query: **27755.779 seconds** (~7 h 42 min 36 s); the data was stale, despite successful retrieval.
- Mean: **120.39743498080082**.
- Population standard deviation: **0.010536816882043902**.
- Minimum / maximum: **120.36645257938915 / 120.42500688448061**.
- Endpoint change: **-0.013186998604481914**.
- Endpoint rate: **-0.0013231102278744395 signal value per simulation minute**.
- Ordinary least-squares regression slope: **-0.00016489704340073697 signal value per simulation minute**.
- Regression interpretation: **descriptive only**, not a claim of physical sensor or plant behavior.

## Findings requiring further work

1. **Answer semantics:** Ollama included the correct quantitative mean, standard deviation and slope, but described the *trend* as provisional. It is the **engineering mapping**, not the statistical calculation, that is provisional.
2. **Freshness:** The persisted record was more than seven hours old. Future answers should explicitly distinguish `latest persisted` from `fresh/live`.
3. **Factual verification:** `answer_validation` remained `NOT_AUTOMATICALLY_VERIFIED`. Numerical agreement in this report was manually inspected, not automatically certified.
4. **Provenance:** The run ID was operator supplied. Shared OPC UA/TimescaleDB provenance and physical sensor binding remain unverified.
5. **Statistical coverage:** A slightly negative fitted slope and negative endpoint change do not alone establish a robust or sustained physical trend.

## Checkpoint status

**Step 2 (quantitative temporal analytics): implemented and locally tested for this example.** Next step: automated factual answer validation with explicit numeric, freshness, semantic-mapping and provenance checks. No claim of generalized multi-function planning or validated physical plant model is made.
