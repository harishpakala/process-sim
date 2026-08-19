# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Current status

**The implementation currently spans Phases 1, 3, 4, and 5. The complete roadmap contains 10 detailed phases organized under four higher-level architectural pillars.**

Implemented today:

- ProfBraatz TEP exposed through `TEPAdapter`
- backend-independent `ProcessSimulator` boundary
- deterministic seeded TEP simulation control
- 41 XMEAS measurements, 12 XMV manipulated variables, and 20 IDV disturbance slots
- TEP engineering names and authoritative measurement units
- asynchronous OPC UA server integration
- simulation lifecycle controls and configurable real-time factor
- OPC UA XMEAS/XMV exposure and XMV write bridge
- canonical `Observation` and `Event` models
- `SimulationRecorder`
- `RunManifest` for simulation provenance
- Parquet persistence with one directory per simulation run
- recording and inspection examples
- `Fault`, `FaultType`, and `FaultManager` primitives
- bias, drift, stuck, and process-disturbance fault definitions
- fault activation/deactivation lifecycle events
- FaultManager integration with TEP XMEAS/XMV publication
- native TEP IDV integration for scenario-managed process disturbances
- YAML/JSON scenario definitions
- executable `ScenarioRunner` connecting faults, TEP, recording, and provenance
- scenario execution example
- fault lifecycle events routable into the canonical recorder
- OPC UA operator XMV changes routable into the canonical event log

The implementation deliberately advances across phases where useful. The roadmap describes the **target architecture and research direction**, not a strict sequential implementation order.

## Four architectural pillars

The 10 detailed implementation phases are grouped into four higher-level architectural and research pillars:

1. **Digital Twin & Simulation** — Phases 1–4
2. **Data & Temporal Infrastructure** — Phase 5
3. **Semantic Digital Thread** — Phases 6–7
4. **Industrial Intelligence** — Phases 8–10

The four-pillar view communicates the overall architecture; the 10-phase roadmap below remains the detailed engineering plan.

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

The semantic-modeling strategy of `process-sim` is grounded in the author's accepted ONTO:NEXUS workshop paper, part of MODELS 2026. The paper establishes the semantic-lifting foundation that this project is intended to extend into a broader industrial digital-thread and temporal-reasoning platform.

> **From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems**  
> Harish Kumar Pakala, Bianca Wiesmayr, Christian Diedrich  
> DOI: https://doi.org/10.1145/3837062.3839557

The paper is **accepted but not yet published**. It should be treated as the research foundation for the semantic-lifting direction, rather than as a description of the complete `process-sim` platform.

## Strategic direction: model first, then lift and reason

The long-term strategy is to establish **proper domain submodel templates first**, semantically annotate and validate those templates using established semantic vocabularies, and only then perform semantic lifting into an ontology-driven knowledge graph.

The central principle is:

> **Model first → semantically annotate → validate → lift → integrate → reason.**

The knowledge graph is not intended to replace the authoritative engineering, business, or operational source models. It is a **semantically lifted, queryable, reasoning-oriented representation** derived from those sources.

The planned pipeline is:

```text
DOMAIN DATA SOURCES
DEXPI | ECAD | ERP | BOM | Operations
        │
        ▼
AAS SUBMODEL TEMPLATES
structure + cardinality + semantics + identity
        │
        ▼
SEMANTIC GROUNDING AND VALIDATION
ECLASS + QUDT + SHACL
        │
        ▼
SEMANTIC LIFTING
AAS Templates → OWL classes / properties / SHACL shapes
AAS Instances → RDF individuals / relationships / provenance
        │
        ▼
CROSS-DOMAIN INDUSTRIAL KNOWLEDGE GRAPH
        │
        ▼
TEMPORAL CONTEXT + ENGINEERING REASONING
        │
        ▼
SPARQL / RULES / GRAPHRAG / AI AGENTS
```

### Template-first semantic modeling

Each major industrial domain should first have a well-defined submodel template before instances are lifted into the KG. The intended template families include:

- **DEXPI / P&ID** — process equipment, piping, instrumentation, connectivity, functional relationships
- **ECAD** — electrical assets, PLC/I/O relationships, signals, endpoints, control topology
- **ERP** — asset/material/master-data references, lifecycle information, procurement context
- **BOM** — EBOM, MBOM, service/spare BOM, quantities, positions, revisions, lifecycle/status, manufacturer and supplier part numbers
- **Operations** — telemetry, alarms, events, states, observations, runs, provenance, and temporal context

Templates should make structure and semantics explicit rather than relying on downstream graph construction to infer them.

### Semantic annotations

Semantic annotation is intended to distinguish at least three complementary dimensions:

- **Classification** — eCl@ss concepts for equipment/material/product classification
- **Quantity kind** — QUDT concepts describing what a measured quantity represents
- **Unit** — QUDT units for engineering quantities

For example, an operational observation may ultimately be represented conceptually as:

```text
Observation_123
    ├── hasQuantityKind ──► QUDT temperature quantity kind
    ├── hasUnit ──────────► QUDT degree-Celsius unit
    └── hasValue ─────────► 78.4
```

The exact semantic identifiers should be authoritative references rather than locally invented labels.

### Semantic lifting

Semantic lifting is a reusable platform capability rather than a one-off transformation for a single domain:

```text
AAS Submodel Template
        │
        ├──► OWL class / properties
        └──► SHACL validation shape

AAS Submodel Instance
        │
        ├──► RDF individuals
        ├──► semantic references
        ├──► cross-domain relationships
        └──► provenance
```

The lifting layer should preserve structural constraints, semantic roles, relationships, deterministic resource identity, and source provenance.

## Cross-domain identity and the digital thread

Canonical identity is a central design problem. The goal is to connect representations of the same real-world asset across engineering, enterprise, and operational systems:

```text
DEXPI:P-101
     ↕
ECAD:P-101
     ↕
BOM:P-101
     ↕
ERP:Material_1000234
     ↕
OPC-UA:P-101
     ↕
Process-simulation representation
```

The KG should therefore provide relationships between source-system identities while preserving those original identifiers and their provenance. Identity resolution should be explicit and deterministic, not an implicit string-matching side effect of graph loading.

The intended digital-thread flow is:

```text
DEXPI + ECAD + BOM + ERP
            │
            ▼
     Semantic Digital Thread
            │
            ▼
     Process Simulation / TEP
            │
            ▼
       OPC UA + Events
            │
            ▼
      Temporal Knowledge
            │
            ▼
      Reasoning / GraphRAG
```

## Temporal data strategy

High-frequency numerical telemetry belongs in a time-series or analytical data layer. Semantic relationships, events, states, provenance, and temporal context belong in the Temporal Knowledge Graph.

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

`GraphDB` should **not become the historian**. Millions of raw high-frequency samples should remain in an efficient time-series/analytical store. The graph should represent selected semantic observations, events, relationships, temporal states, provenance, and references back to the underlying numerical data.

The intended storage evolution is:

```text
SimulationRecorder
       │
       ├── MemoryStorage
       └── FileStorage
              └── Parquet

Future

SimulationRecorder
       ├── Parquet / historical storage
       ├── Time-Series / historian storage
       └── Temporal Knowledge Graph
```

## Observation vs event

```text
OBSERVATIONS
123.0 h   XMV10 = 16.0
123.1 h   XMV10 = 16.2
123.2 h   XMV10 = 16.8

EVENTS
123.0 h   Operator changed XMV10: 16 → 20
125.4 h   FaultActivated: reactor temperature bias
128.1 h   FaultDeactivated: reactor temperature bias
```

Events should be generated by the subsystem where they occur, preserving causality and provenance, rather than inferred by repeatedly polling the graph.

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
                         ScenarioRunner
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

## Current OPC UA namespace

```text
Objects
└── TEP
    ├── Simulation
    │   ├── TimeHours
    │   ├── Running
    │   ├── RealTimeFactor
    │   ├── Start()
    │   ├── Stop()
    │   └── Reset()
    ├── Measurements
    │   └── XMEAS1 ... XMEAS41
    └── ManipulatedVariables
        └── XMV1 ... XMV12
```

Application namespace URI:

```text
urn:process-sim:opcua
```

The development server currently uses `opc.tcp://0.0.0.0:4841/process-sim/` because port 4840 was occupied in the development environment.

## Fault and scenario engineering

The fault layer is connected to the TEP adapter and scenario execution path:

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

Faults contain an ID, type, target, timing, magnitude/value, and metadata. They can be scheduled and queried by simulation time.

Signal-level faults operate at the TEP adapter boundary. Process disturbances are intentionally different: they are synchronized to the TEP model's native IDV interface rather than being simulated as measurement or actuator offsets.

### Scenario definition

Scenarios can be stored as YAML or JSON. For example:

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

The scenario runner turns this definition into one reproducible recorded experiment:

```text
Scenario
   ↓
FaultManager
   ↓
TEPAdapter
   ↓
SimulationRecordingSession
   ↓
observations.parquet + events.parquet + metadata.json
```

Run a scenario with:

```bash
python examples/run_scenario.py examples/scenarios/reactor_sensor_and_process_fault.yaml --hours 2 --seed 42
```

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

This provides the foundation for reproducible scenario and fault experiments.

## Recording foundation

`process-sim` separates **continuous observations** from **discrete semantic events**.

```text
Simulation
    │
    ├── Observations ──► SimulationRecorder ──► Parquet / future TSDB
    │
    └── Events ────────► SimulationRecorder ──► event log / future Temporal KG
```

`Observation` is used for values such as XMEAS and XMV. TEP XMEAS observations carry engineering units from the reference mapping. XMV units remain unset until an authoritative source is identified.

`Event` is reserved for semantically meaningful occurrences such as operator actions, faults, alarms, controller transitions, and simulation lifecycle changes.

The recorder does not control or slow the simulator. It is intentionally pull-based: callers decide when to capture a snapshot.

## Recording a TEP run

Install the recording dependencies:

```bash
pip install -r requirements-recording.txt
```

Because the project currently uses a `src/` layout, either configure `process-sim/src` in PyDev or set `PYTHONPATH` in a terminal. For example in PowerShell:

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

Inspect the latest run:

```bash
python examples/inspect_tep_run.py
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

The project uses **ten detailed implementation phases**, grouped into the four architectural pillars above. The phases are **not a rigid waterfall**; the implementation advances across them where doing so establishes useful foundations.

### Phase 1 — TEP Reference and Python Simulation Integration — FOUNDATION COMPLETE

- ProfBraatz scientific reference
- backend-independent simulator boundary
- TEP adapter
- deterministic stepping and seeded runs
- measurements, manipulated variables, states, and disturbances
- engineering mappings and XMEAS units
- canonical observations/events

Remaining work is deeper numerical validation and reproducibility tooling.

### Phase 2 — Industrial Twin Core — IN PROGRESS

- canonical plant and asset model
- equipment, instruments, tags, and functional relationships
- canonical identifiers and source-system identifiers
- deterministic simulation clock/orchestration
- lifecycle and run management
- experiment metadata
- operating states and state transitions
- source-generated events
- fault/scenario integration

The core remains independent of TEP so future process models can become additional backends.

### Phase 3 — Fault Injection and Scenario Engineering — FOUNDATION IMPLEMENTED

Implemented:

- `Fault` model
- `FaultType`
- `FaultManager`
- bias, drift, stuck, and process-disturbance definitions
- scheduled activation windows
- XMEAS/XMV signal fault application
- native TEP IDV1..IDV20 process-disturbance integration
- YAML/JSON scenario loading
- `ScenarioRunner`
- `FaultActivated` / `FaultDeactivated` events
- run provenance for scenario experiments

Next:

- scenario schema validation and richer scheduling semantics
- noise, saturation, intermittent, and combined fault modes
- actuator/sensor failure modes
- controller and communication faults
- scenario libraries and experiment comparison

### Phase 4 — OPC UA Integration — INITIAL IMPLEMENTATION COMPLETE

Implemented:

- stable application namespace
- TEP object
- 41 XMEAS and 12 XMV nodes
- simulation time and running state
- Start/Stop/Reset methods
- configurable real-time factor
- explicit XMV write bridge
- asynchronous simulation loop
- operator XMV event integration

Next:

- semantic engineering names and units
- OPC UA EUInformation and quality/status/timestamps
- richer alarms and events
- external SCADA/HMI integration tests
- security and deployment configuration

### Phase 5 — Time-Series and Temporal Knowledge Infrastructure — RECORDING FOUNDATION IMPLEMENTED

Implemented foundation:

- canonical `Observation` and `Event` models
- `SimulationRecorder`
- run manifests and provenance
- storage-neutral recording session
- Parquet persistence
- observation/event separation
- operator and fault lifecycle event recording

Next:

- historian/time-series backend integration
- temporal event model expansion
- temporal knowledge graph schema
- event-to-observation correlation
- historical query and replay interfaces

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

## Research direction

The strongest research direction is not simply to build a larger SCADA or simulation platform. The intended contribution is a **provenance-aware industrial digital thread** that connects:

```text
Engineering Models
       │
       ├── DEXPI / P&ID
       ├── ECAD
       ├── BOM
       └── ERP
              │
              ▼
       Semantic Digital Thread
              │
              ▼
       Process Simulation
              │
              ▼
       Telemetry + Events + Faults
              │
              ▼
       Temporal Knowledge Graph
              │
              ▼
       GraphRAG / Industrial AI
```

The TEP should serve as a controlled, reproducible experimental environment. Future evaluation should compare time-series-only retrieval against combinations of time-series data, engineering knowledge, temporal events, and provenance-aware graph reasoning.

The intended evaluation questions include:

1. Does temporal knowledge improve operational-context retrieval compared with time-series-only retrieval?
2. Do engineering relationships plus telemetry improve fault and root-cause identification?
3. Does explicit provenance reduce unsupported or unverifiable AI conclusions?
4. Can the same semantic identity connect engineering, enterprise, simulation, and operational representations consistently?

The long-term goal is an industrial platform in which **simulation, digital-thread integration, temporal data, semantic reasoning, and industrial AI form one reproducible architecture rather than separate systems**.
