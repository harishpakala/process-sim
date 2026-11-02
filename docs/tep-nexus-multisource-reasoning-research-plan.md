# TEP NEXUS — Research pivot: heterogeneous-source reasoning

**Status:** experimental design, not implementation or a claim of passed reasoning tests.  
**Research objective:** Determine whether a constrained LLM-based engineering assistant can integrate AAS/GraphDB semantic relationships, TimescaleDB temporal observations, and provenance/uncertainty metadata to produce evidence-supported answers.

## Scope

The Tennessee Eastman Process (TEP) is an established process-control benchmark, not the object of controller-performance evaluation in this work. Do not add PID, nonlinear-control, simulator-throughput, or model-latency performance benchmarks to this research milestone. Prior 34/34 function coverage and 36/36 integration-case success are baseline evidence for retrieval and grounded answer generation; they do **not** establish multi-function reasoning or causal explanation.

## System boundary and attribution

- **LLM:** interprets natural language, produces constrained query plans, and verbalizes evidence.
- **Deterministic software:** validates plans, resolves GraphDB mappings, retrieves TimescaleDB observations, computes numerical temporal summaries, validates answer assertions, and repairs failed answers.
- **Sources:** GraphDB/AAS semantics; TimescaleDB observations; provenance and verification status.
- Report end-to-end correctness separately from *unrepaired LLM answer* correctness and repair dependence. Do not attribute deterministic calculations to LLM inference.

## Proposed 12-case reasoning benchmark (not yet executable)

Each item requires an evidence packet, a source-by-source trace, and a gold answer or explicit insufficiency judgment. The current planner supports one explicit function identifier only; multi-function cases are **blocked until a safe multi-function plan and retrieval implementation exists**.

| ID | Dimension | Candidate question | Required evidence | Status |
|---|---|---|---|---|
| R01 | Semantic grounding | What engineering function does FI_101 denote, and what operational signal is linked to it? | GraphDB mapping | Existing single-function path; semantic labels must be verified |
| R02 | Semantic + temporal | What is FI_101's latest persisted observation and ten-minute trend? | GraphDB + TimescaleDB | Existing single-function path |
| R03 | Temporal interpretation | Is FI_101 increasing or decreasing in the last ten simulation minutes, and what are the endpoint change and fitted slope? | Time-windowed observations, deterministic analytics | Existing single-function path |
| R04 | Provenance | Can the FI_101 reading be described as physically verified and live? | Observation timestamps and provenance limitations | Existing path; expected qualified answer |
| R05 | Cross-function comparison | Compare FI_101 and PI_101 trends over the same simulation-time interval. | Two mappings, two aligned time series | **Blocked: multi-function planner/retrieval** |
| R06 | Relative change | Which of FI_101 and PI_101 changed more in relative terms during the shared interval? | Two series, nonzero baselines, deterministic percentage change | **Blocked** |
| R07 | Temporal co-occurrence | Did FI_101 and PI_101 both change during the selected interval? | Two aligned series, explicit criterion for change | **Blocked** |
| R08 | Semantic context | Are FI_101 and VC_101 connected by a documented AAS relationship? | Explicit GraphDB path; do not infer from naming | **Blocked until relationship evidence exists** |
| R09 | Context + behavior | For an evidenced related measurement and actuator, summarize the measurement's observed trend without claiming the actuator caused it. | Verified semantic link plus temporal observations | **Blocked** |
| R10 | Unsupported causality | Did VC_101 cause a change in FI_101? | Intervention/causal evidence, not mere correlation | Expected abstention unless independent causal evidence supplied |
| R11 | Insufficient source | What is FI_101's physical sensor calibration certificate? | Explicit calibration document | Expected evidence-insufficiency response |
| R12 | Conflicting or missing evidence | What should the engine conclude if a mapping is ambiguous or one required series is absent? | Controlled evidence fixtures | Expected fail-closed/qualified response |

These are **candidate research questions**, not assertions about physical correspondences or observed trends. Confirm labels and relationships from the actual GraphDB evidence before finalizing any gold answer.

## Evaluation rubric

For each case record:
1. **Plan validity:** requested identifiers, time interval, and intended sources correctly identified.
2. **Source coverage:** every required source consulted or its absence explicitly recorded.
3. **Evidence correctness:** retrieved mapping and numerical values match independent deterministic reference calculations.
4. **Cross-source synthesis:** statements that require multiple sources are supported by each necessary source.
5. **Uncertainty and provenance:** provisional mapping, unverified physical binding and shared-run provenance stated appropriately.
6. **Unsupported-claim avoidance:** no causal, physical, or live-data claim without evidence.
7. **Answer attribution:** score the raw LLM answer and final repaired answer separately.

Score each dimension as pass/fail/not-applicable with source-level justification. An answer repaired by deterministic software counts toward **end-to-end system success**, not raw LLM reasoning success.

## Implementation gates

**Gate A — freeze baseline:** preserve existing 34-function reports and 36-case summary; no further generic function coverage expansion.

**Gate B — evidence inventory:** inspect GraphDB relationships, coverage snapshots, observation schemas, and whether data are genuinely aligned by simulation time. Document available and absent relationships.

**Gate C — constrained multi-function support:** introduce a new explicit list-of-functions plan schema (do not weaken existing single-function validation); cap count and history windows; revalidate each mapping against GraphDB; retrieve each series read-only; align on simulation time with declared join/tolerance; enforce bounded retrieval and fail-closed errors.

**Gate D — independent oracle:** compute endpoint changes, slopes, relative changes and time overlap deterministically; keep graph paths and source identifiers in the evidence packet.

**Gate E — reasoning evaluation:** execute only evidence-supported cases, evaluate raw and repaired answers separately, record abstention quality, and write research findings. Do not report blocked cases as failed executions.

## Existing limitations

Engineering mappings are provisional; physical sensor binding and shared physical run provenance are unverified. Operator-supplied run ID and local observation coverage do not establish causality. The previous benchmark established limited-scope correctness after deterministic repair, not autonomous LLM quantitative reasoning.

## Literature context

Downs, J. J. and Vogel, E. F. (1993). *A plant-wide industrial process control problem*. Computers & Chemical Engineering, 17(3), 245–255. https://doi.org/10.1016/0098-1354(93)80018-I
