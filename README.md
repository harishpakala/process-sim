# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Current status

**The implementation currently spans Phases 1, 3, 4, and 5. The current branch also contains the first reproducible controlled-experiment framework on top of the recording infrastructure.** The complete roadmap contains 10 detailed phases organized under four architectural pillars.

Implemented and verified at the platform level:

- ProfBraatz TEP exposed through `TEPAdapter`
- backend-independent `ProcessSimulator` boundary
- deterministic seeded TEP simulation control
- 41 XMEAS measurements, 12 XMV manipulated variables, and 20 IDV disturbance slots
- authoritative XMEAS engineering units
- asynchronous OPC UA integration
- simulation lifecycle controls and configurable real-time factor
- OPC UA XMEAS/XMV exposure and XMV write bridge
- canonical `Observation` and `Event` models
- `SimulationRecorder` and `RunManifest`
- Parquet persistence with one directory per run
- recording and inspection examples
- `Fault`, `FaultType`, and `FaultManager`
- bias, drift, stuck, and process-disturbance fault definitions
- scheduled fault activation/deactivation lifecycle events
- native TEP IDV integration for scenario-managed process disturbances
- YAML/JSON scenario definitions
- executable `ScenarioRunner`
- fault lifecycle events and OPC UA operator XMV changes in the canonical event log
- declarative `Experiment` / `GroundTruth` models and `ExperimentRunner`
- experiment provenance persisted in run metadata
- initial benchmark matrix and controlled experiment fixtures

### First controlled experiment result

Experiment `reactor_cooling_bias_001` has now been executed end-to-end and inspected successfully:

```text
Run:              3972cf14-1e97-4259-a758-5d9f2ef6026c
Scenario:         reactor_sensor_bias
Seed:             42
Simulated time:   0.0 → 2.0 h
Native timestep:  1 s
Variables:        53
Observation rows: 381,653
Event rows:       4
```

The recorded lifecycle is:

```text
0.0 h   SimulationStarted
1.0 h   FaultActivated     XMEAS9
1.5 h   FaultDeactivated   XMEAS9
2.0 h   SimulationCompleted
```

The experiment therefore establishes the **deterministic execution and temporal ground-truth layer**: the declared fault identity and boundaries are present in the persisted event log at the expected simulation times. The observation count is consistent with 7,201 snapshots × 53 variables when recording every native step.

This does **not yet establish a quantitative process-response result**. The next experimental layer is to measure the response of `XMEAS9` and its related variables such as `XMV10` and `XMEAS21` during pre-fault, fault, and post-fault windows.

Simulation time is accelerated; the 2-hour experiment does not run for two hours of wall-clock time. The `real_time_factor` is currently unset for this experiment path.

The implementation deliberately advances across phases where useful. The roadmap describes the target architecture and research direction, not a strict sequential implementation order.

## Four architectural pillars

1. **Digital Twin & Simulation** — Phases 1–4
2. **Data & Temporal Infrastructure** — Phase 5
3. **Semantic Digital Thread** — Phases 6–7
4. **Industrial Intelligence** — Phases 8–10

```text
                INDUSTRIAL AI
                     │
             ┌───────┴────────┐
             │ 4. Intelligence│
             │ GraphRAG / AI  │
             └───────┬────────┘
                     │
          ┌──────────┴──────────┐
          │ 3. Semantic         │
          │ Digital Thread      │
          │ AAS / eCl@ss / QUDT │
          │ DEXPI / ECAD / BOM  │
          └──────────┬──────────┘
                     │
          ┌──────────┴──────────┐
          │ 2. Temporal Data    │
          │ TSDB + Events + TKG │
          └──────────┬──────────┘
                     │
          ┌──────────┴──────────┐
          │ 1. Digital Twin     │
          │ TEP / Faults / OPCUA│
          └─────────────────────┘
```

## Research foundation

The semantic-modeling strategy is grounded in the author's **accepted but not yet published** ONTO:NEXUS workshop paper, part of MODELS 2026:

> **From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems**  
> Harish Kumar Pakala, Bianca Wiesmayr, Christian Diedrich  
> DOI: https://doi.org/10.1145/3837062.3839557

The paper establishes the semantic-lifting foundation that `process-sim` is intended to extend into a broader industrial digital-thread and temporal-reasoning platform.

## Strategic direction

The long-term strategy is:

> **Model first → semantically annotate → validate → lift → integrate → reason.**

The knowledge graph is not intended to replace authoritative engineering, business, or operational source models. It is a semantically lifted, queryable, reasoning-oriented representation derived from those sources.

```text
DEXPI | ECAD | ERP | BOM | Operations
        │
        ▼
AAS SUBMODEL TEMPLATES
        │
        ▼
SEMANTIC GROUNDING + VALIDATION
ECLASS + QUDT + SHACL
        │
        ▼
SEMANTIC LIFTING
AAS → OWL / SHACL / RDF
        │
        ▼
CROSS-DOMAIN INDUSTRIAL KG
        │
        ▼
TEMPORAL + ENGINEERING REASONING
        │
        ▼
SPARQL / RULES / GRAPHRAG / AI AGENTS
```

Template families planned for the digital thread include DEXPI/P&ID, ECAD, ERP, BOM, and Operations. Canonical identity and provenance are first-class design concerns.

## Temporal data strategy

High-frequency numerical telemetry belongs in a time-series or analytical layer. Semantic relationships, events, states, provenance, and temporal context belong in a Temporal Knowledge Graph.

```text
Time-series layer
XMEAS9 @ t = 120.0 h = 121.6 deg C
XMEAS9 @ t = 120.1 h = 121.7 deg C
...

Temporal KG
Operator ──changed──► XMV10
XMV10 ──affects──► Reactor Cooling
Fault ──activatedAt──► simulation time
```

`GraphDB` should not become the historian. Raw high-frequency samples should remain in efficient analytical storage; the graph should represent selected semantic observations, events, relationships, temporal states, provenance, and references to numerical data.

## Current architecture

```text
                           process-sim
                                │
                ┌───────────────┼────────────────────┐
                │               │                    │
           TEPAdapter      FaultManager           OPC UA
                │               │                    │
                └───────────────┼────────────────────┘
                                │
                 ScenarioRunner / ExperimentRunner
                                │
                           Simulation
                                │
                     ┌──────────┴──────────┐
                     │                     │
                Observations            Events
                     │                     │
                     └──────────┬──────────┘
                                ▼
                        Recording Session
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
               Parquet data          Run Manifest
                    │                       │
                    └───────────┬───────────┘
                                ▼
                     future TSDB / Temporal KG
```

## Fault and scenario engineering

```text
Scenario YAML / JSON
        │
        ▼
   ScenarioRunner
        │
   ┌────┴──────────┐
   ▼               ▼
FaultManager    RunManifest
   │
   ├── Bias ─────────────► XMEAS signal transformation
   ├── Drift ────────────► XMEAS/XMV signal transformation
   ├── Stuck ────────────► XMEAS/XMV signal transformation
   └── Process disturbance ─► native TEP IDV1..IDV20
                                      │
                                      ▼
                                TEP process model
```

Signal-level faults operate at the TEP adapter boundary. Process disturbances are synchronized to the TEP model's native IDV interface.

Example:

```yaml
scenario: reactor_sensor_and_process_fault
metadata:
  random_seed: 42
faults:
  - id: reactor-temperature-bias
    type: bias
    target: XMEAS9
    magnitude: 5.0
    start: 1.0
    duration: 0.5
  - id: process-disturbance
    type: process_disturbance
    target: IDV6
    start: 1.5
    duration: 0.25
```

## Controlled experiments

Experiments add scientific context around scenario execution:

```text
Experiment YAML / JSON
        │
        ├── Scenario ───────► ScenarioRunner
        │                         │
        └── Ground Truth         TEPAdapter
                                  │
                                  ▼
                         Recording Session
                                  │
                         observations + events
                                  │
                                  ▼
                             Run Manifest
```

The experiment layer is intentionally thin. `ScenarioRunner` remains the owner of simulation orchestration, fault synchronization, recording cadence, storage, and simulator provenance. `ExperimentRunner` adds experiment identity, declared ground truth, and benchmark metadata.

Current fixture:

`examples/experiments/reactor_cooling_bias_001.yaml`

Current benchmark families:

1. normal baseline
2. sensor bias
3. sensor drift
4. actuator stuck
5. process disturbance
6. combined faults

The benchmark matrix is a specification, not yet an automated batch executor.

### Evidence status

The current experiment evidence establishes:

- reproducible experiment configuration
- persisted experiment and ground-truth metadata
- complete observation coverage for the configured duration
- fault activation and deactivation events at exact declared simulation boundaries
- simulation lifecycle events and provenance

Still to be established experimentally:

- quantitative sensor-response magnitude
- baseline/fault/recovery statistics
- response latency and settling behavior
- controller response in related variables
- multi-seed repeatability
- fault-attribution and detection metrics
- comparisons across benchmark families

## Run provenance

Each recording run has a `RunManifest` containing:

```text
Run
├── run_id
├── simulator
├── backend
├── backend_version
├── random_seed
├── real_time_factor
├── scenario
├── started_at
├── completed_at
└── metadata
```

Experiment metadata and declared ground truth are persisted under the run metadata for reproducibility.

## Recording a TEP run

Install the recording dependencies:

```bash
pip install -r requirements-recording.txt
```

For the current `src/` layout, set `PYTHONPATH` when needed. PowerShell:

```powershell
$env:PYTHONPATH="$PWD\src"
```

Record a one-hour Python-backend run:

```bash
python examples/record_tep_run.py --hours 1
```

Record every 10 native steps:

```bash
python examples/record_tep_run.py --hours 1 --interval 10
```

Inspect a run:

```bash
python examples/inspect_tep_run.py --run-id <run-id> --root data/runs
```

Run the controlled experiment fixture:

```bash
python examples/run_experiment.py \
  examples/experiments/reactor_cooling_bias_001.yaml \
  examples/scenarios/reactor_sensor_bias.yaml \
  --output data/runs
```

Each run is stored as:

```text
data/
└── runs/
    └── <run-id>/
        ├── metadata.json
        ├── observations.parquet
        └── events.parquet
```

Parquet is the current portable intermediate format, not the final production historian architecture.

## Roadmap

The ten phases are grouped into the four architectural pillars. They are not a rigid waterfall; implementation advances where a foundation supports the research program.

### Phase 1 — TEP Reference and Python Simulation Integration — FOUNDATION COMPLETE

Completed foundation:

- ProfBraatz scientific reference
- backend-independent simulator boundary
- TEP adapter
- deterministic stepping and seeded runs
- measurements, manipulated variables, states, and disturbances
- engineering mappings and XMEAS units
- canonical observations/events

Next: deeper numerical validation and reproducibility tooling.

### Phase 2 — Industrial Twin Core — IN PROGRESS

Target:

- canonical plant and asset model
- equipment, instruments, tags, and functional relationships
- canonical and source-system identifiers
- deterministic simulation clock/orchestration
- lifecycle and run management
- operating states and state transitions
- source-generated events
- richer asset relationships independent of TEP

### Phase 3 — Fault Injection and Scenario Engineering — FOUNDATION IMPLEMENTED

Completed:

- `Fault`, `FaultType`, `FaultManager`
- bias, drift, stuck, and process-disturbance definitions
- scheduled activation windows
- XMEAS/XMV signal fault application
- native TEP IDV1..IDV20 integration
- YAML/JSON scenario loading
- `ScenarioRunner`
- fault lifecycle events
- scenario run provenance

Next:

- schema validation and richer scheduling semantics
- noise, saturation, intermittent, and combined fault modes
- controller and communication faults
- scenario libraries and experiment comparison

### Phase 4 — OPC UA Integration — INITIAL IMPLEMENTATION COMPLETE

Completed:

- stable application namespace
- TEP object
- 41 XMEAS and 12 XMV nodes
- simulation time and running state
- Start/Stop/Reset methods
- configurable real-time factor
- XMV write bridge
- asynchronous simulation loop
- operator XMV event integration

Next:

- semantic engineering names and units
- OPC UA EUInformation and quality/status/timestamps
- richer alarms and events
- external SCADA/HMI integration tests
- security and deployment configuration

### Phase 5 — Time-Series, Experiments, and Temporal Knowledge Infrastructure — FOUNDATION IMPLEMENTED

Completed foundation:

- canonical `Observation` and `Event` models
- `SimulationRecorder`
- run manifests and provenance
- storage-neutral recording session
- Parquet persistence
- observation/event separation
- operator and fault lifecycle event recording
- declarative experiment definitions
- experiment/ground-truth provenance
- initial benchmark matrix
- first end-to-end controlled experiment with exact temporal ground-truth events

Next:

- automated quantitative response analysis
- baseline/fault/recovery metrics
- multi-seed experiment execution
- automated benchmark aggregation
- historian/time-series backend integration
- temporal event model expansion
- event-to-observation correlation
- temporal knowledge graph schema and replay/query interfaces

### Phase 6 — Engineering & Semantic Digital Thread — PLANNED

- AAS submodel templates
- domain template governance and validation
- eCl@ss classification
- QUDT quantity kinds and units
- OWL/SHACL semantic foundation
- deterministic semantic lifting
- DEXPI/P&ID integration
- ECAD integration
- cross-domain asset identity
- engineering provenance

The guiding workflow is **model first → semantically annotate → validate → lift → integrate → reason**.

### Phase 7 — BOM & Enterprise Integration — PLANNED

- EBOM, MBOM, service/spare BOM
- material and asset master data
- ERP references
- manufacturer and supplier part identities
- quantities, positions, revisions, lifecycle/status
- enterprise-to-engineering identity resolution
- cross-domain digital-thread relationships

### Phase 8 — Web SCADA / HMI — PLANNED

- browser-based operational interface
- live process visualization
- trends and historical views
- alarms and events
- scenario controls
- operator actions
- engineering-name and semantic metadata integration

### Phase 9 — Knowledge Graph & GraphRAG — PLANNED

- industrial knowledge graph
- temporal knowledge graph
- SPARQL and engineering queries
- competency-question-driven reasoning
- graph-based retrieval
- GraphRAG over engineering, operational, and enterprise context
- evidence and provenance-aware answers

### Phase 10 — Industrial AI Platform — PLANNED

- industrial agents
- fault diagnosis and root-cause reasoning
- temporal reasoning over process behavior
- engineering-aware recommendations
- evidence-backed operational assistance
- controlled agent actions
- benchmarked evaluation against time-series-only and graph-enhanced baselines

## Research progression

The research sequence is intentionally evidence-driven:

```text
Controlled Digital Twin
        ↓
Reproducible Operational Data
        ↓
Semantically Integrated Digital Thread
        ↓
Temporal + Engineering Reasoning
        ↓
Evidence-Grounded Industrial AI
```

For the immediate experimental program, the next step is **variable-level response analysis** of controlled fault runs before expanding into semantic reasoning or GraphRAG.

The intended evaluation questions are:

1. Does temporal knowledge improve operational-context retrieval compared with time-series-only retrieval?
2. Do engineering relationships plus telemetry improve fault and root-cause identification?
3. Does explicit provenance reduce unsupported or unverifiable AI conclusions?
4. Can the same semantic identity connect engineering, enterprise, simulation, and operational representations consistently?

The TEP should remain a controlled, reproducible experimental environment while the platform grows toward a provenance-aware industrial digital thread.