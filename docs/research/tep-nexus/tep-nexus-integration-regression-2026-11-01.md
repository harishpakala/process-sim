# TEP NEXUS — End-to-end integration regression checkpoint

**Execution timestamp (UTC):** 2026-11-01T22:55:19.887652+00:00  
**Evidence source:** Operator-supplied `tep_nexus_ollama_planned_query(1).json` from a local execution.  
**Model:** `llama3.1:8b`  
**Status reported by pipeline:** `COMPLETED`  
**Answer validation:** `NOT_AUTOMATICALLY_VERIFIED`

## Test question

> For engineering function TI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance.

## Plan

The Ollama planner returned `latest_and_history` for `TI_101`, with a 10-minute history window, `include_asset: true`, and `include_provenance: true`. The deterministic plan validator accepted this plan.

## Semantic and temporal evidence

- Engineering function: `TI_101`
- AAS function reference: `https://aas.example.com/TI_101`
- Operational signal: `XMEAS9`
- Mapping status: `PROVISIONAL_ENGINEERING_MATCH`
- Temporal source: TimescaleDB; engineering semantic source: GraphDB
- Operator-supplied run ID: `10cfb1d1-2984-4932-8207-dc430ed60c2b`
- Latest persisted observation: simulation time `3514.0 s`, value `120.38819508324035`
- Observation timestamp: `2026-11-01T23:31:16.836489+01:00`
- Record age at query: `1457.051 s` (about 24 minutes 17 seconds)
- History basis: **simulation time**, requested 10 minutes; 201 samples; `truncated: false`
- History minimum: `120.36645257938915`
- History maximum: `120.42500688448061`
- First observation: `2916.0 s`, value `120.40138208184483`
- Last observation: `3514.0 s`, value `120.38819508324035`
- Endpoint change: approximately **-0.013187** (last minus first). This is **not** a regression slope or proof of a sustained trend.

The report also included an associated asset URI. Its mapping remains provisional; the physical sensor binding and shared run provenance are **not verified**.

## Results and limitations

**Observed success:** The local pipeline reported successful constrained NL-to-plan processing, GraphDB semantic resolution, TimescaleDB observation retrieval, and Ollama answer generation. The answer reproduced the latest value, associated asset, and unverified provenance caveat.

**Finding 1 — freshness:** The latest persisted record was approximately 24 minutes old when retrieved. The result is a successful *latest-persisted-record query*, not evidence that the underlying source was currently updating.

**Finding 2 — quantitative trend:** The generated answer called the trend provisional because the engineering mapping was provisional. This conflates semantic mapping confidence with temporal signal behavior. No deterministic regression slope, mean, or variability was supplied in the evidence.

**Finding 3 — answer verification:** `answer_validation` remained `NOT_AUTOMATICALLY_VERIFIED`; the pipeline's `COMPLETED` status must not be interpreted as independent factual validation.

**Finding 4 — provenance:** Shared OPC UA/TimescaleDB run identity and physical sensor binding were not verified. The engineering mapping must not be presented as an approved physical correspondence.

## Separate offline testing evidence

The operator reported running `python -m unittest discover -s tests -p "test_tep_nexus_query_planner.py" -v`: **12 tests, 12 passed, 0 failures**, in 0.004 seconds. This is an operator-reported local test run, not a CI verification. The tests cover constrained plan validation; they do not establish Ollama intent accuracy or end-to-end correctness.

## Next research milestones (not yet implemented at this checkpoint)

1. Deterministic temporal analytics (mean, variability, endpoint delta, regression slope, coverage).
2. Automated factual answer validation against retrieved evidence, including freshness and mapping/provenance caveats.
3. Generalized multi-function semantic query planning and corresponding evaluation fixtures.
4. Automated offline and integration regression tests, benchmark questions, and reproducible paper-ready results.

**Scope note:** This checkpoint documents one operator-provided local report. It does not independently rerun services, validate the source database, or certify an approved engineering mapping. Do not commit credentials or unsanitized operational reports.
