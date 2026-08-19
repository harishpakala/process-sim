# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Current status

**Phase 1 foundation complete; Phase 3 fault/scenario foundation implemented; Phase 4 OPC UA initial integration complete; Phase 5 recording foundation implemented.**

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

The project uses ten architectural phases. The phases are **not a rigid waterfall**; the implementation advances across them where doing so establishes useful foundations.

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
- subscriptions and client integration tests
- process/equipment hierarchy
- FaultManager scenario controls
- richer native process-disturbance controls

### Phase 5 — Time-Series and Temporal Knowledge Infrastructure — IMPLEMENTATION STARTED

Implemented:

- canonical Observation/Event models
- engineering units for XMEAS observations
- in-memory recorder
- Parquet persistence
- run manifests/provenance
- simulation lifecycle events
- operator events
- fault lifecycle events
- TEP recording and inspection examples
- scenario-driven recorded experiments

Next:

- evaluate production TSDB/historian choices using real workload requirements
- temporal KG schema
- event/relationship model
- graph-to-time-series references
- quality/status/timestamp model
- retention and archival strategy

### Phase 6 — Semantic Industrial Models and Digital Thread

This phase is now a central research and implementation direction rather than simply a data-import task.

The workflow is:

```text
1. Establish authoritative Submodel Templates
2. Define structure, cardinality, identity, and constraints
3. Semantically annotate with ECLASS and QUDT
4. Validate templates and instances with SHACL
5. Semantically lift templates and instances into OWL/RDF
6. Preserve provenance and source-system identifiers
7. Resolve canonical cross-domain identities
8. Integrate the resulting knowledge graph
9. Add engineering and temporal reasoning
```

Planned domain model families:

- DEXPI / P&ID
- ECAD
- BIM / IFC
- CAD / 3D
- ERP
- EBOM / MBOM / service and spare BOM
- engineering documents, specifications, and datasheets
- operational observations, alarms, events, and states

The objective is not merely to convert files into RDF. It is to establish **validated semantic submodel templates first**, then provide a generic and deterministic semantic-lifting layer that can be reused across domains.

### Phase 7 — BOM and Enterprise Integration

Support EBOM, MBOM, service/spare BOM, procurement relationships, revisions, quantities, lifecycle/status, manufacturer/supplier part numbers, ECLASS classifications, and ERP references.

BOM information is a first-class part of the digital thread because operational reasoning should eventually be able to connect an affected asset to its physical components, replacement parts, suppliers, and enterprise context.

### Phase 8 — Web SCADA / HMI

Build a web control-room experience on the canonical model, including plant mimic, telemetry, trends, alarms, controller faceplates, simulation controls, fault injection, scenarios, equipment hierarchy, documents, P&IDs, and BOM information.

### Phase 9 — Knowledge, Documents, RAG and GraphRAG

Add document ingestion, metadata, chunking, embeddings, vector retrieval, graph retrieval, GraphRAG, evidence/provenance, procedures, and technical knowledge. Temporal operational context will be available alongside static engineering knowledge.

GraphRAG is deliberately placed **after** semantic modeling, identity, validation, lifting, and temporal foundations. The goal is to reason over a structured industrial knowledge base rather than use an LLM as a substitute for modeling.

### Phase 10 — Industrial AI Platform

Build an AI assistant capable of reasoning over operational data, temporal events, process topology, alarms, faults, controllers, engineering relationships, maintenance history, BOM information, procedures, historical trends, and simulation results with traceable evidence.

The research goal is to evaluate whether combining semantic digital-thread context with temporal operational data improves diagnosis, root-cause analysis, impact analysis, maintenance reasoning, and evidence traceability.

## Research and evaluation direction

The next major research step is to turn the platform into a **controlled experimental environment for industrial digital-thread reasoning**.

`process-sim` can provide reproducible ground truth by combining:

```text
Engineering context
DEXPI / ECAD / BOM / ERP
          │
          ▼
     Digital Thread
          │
          ▼
      TEP simulation
          │
     ┌────┴────┐
     ▼         ▼
 Faults     Operator actions
     │         │
     └────┬────┘
          ▼
   Telemetry + Events
          │
          ▼
    Temporal Knowledge
          │
          ▼
   Reasoning / GraphRAG
```

A future benchmark should compare progressively richer representations, for example:

```text
A. Time-series only
B. Time-series + events
C. Time-series + operational KG
D. Engineering digital thread + operational KG
E. Full temporal digital thread + reasoning
```

Potential evaluation dimensions include:

- fault identification accuracy
- root-cause identification accuracy
- temporal localization
- evidence precision and recall
- cross-domain relationship retrieval
- unsupported-claim / hallucination rate
- reasoning and retrieval latency
- traceability from conclusions back to source evidence

The TEP should be treated as a **controlled scientific benchmark and experimental process model**, not as a claim of validation against a real industrial plant.

## Target architecture

```text
                           INDUSTRIAL AI
                       GraphRAG / AI Agents
                                │
                                ▼
                    INDUSTRIAL KNOWLEDGE GRAPH
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
        Engineering        Operations          Business
        DEXPI / P&ID       OPC UA / SCADA      ERP / ECLASS
        ECAD / BIM         Historian/TSDB      BOM
        CAD / 3D           Alarms / Events
              │                 │                 │
              └─────────────────┼─────────────────┘
                                │
                         INDUSTRIAL TWIN
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
           Process Simulation            Data Infrastructure
                 │                             │
          ┌──────┴──────┐              ┌───────┴────────┐
          │             │              │                │
         TEP          DWSIM       Time-Series       Event Log
          │                            /Parquet          │
          └────────────┬─────────────────┴───────────────┘
                       │
                  Canonical Identity
                       │
                 Temporal Context
```

## Design principles

1. **Reference-model integrity** — preserve reference TEP behavior.
2. **Separation of concerns** — physics, orchestration, industrial integration, storage, visualization, and AI remain separate.
3. **Canonical identity** — systems map to shared plant/asset identities.
4. **Graph as semantic backbone** — the graph represents relationships, context, events, and temporal semantics.
5. **Time-series where time-series belongs** — high-frequency numeric telemetry stays in an efficient data layer.
6. **Observation/event separation** — continuous measurements are distinct from semantic occurrences.
7. **Asynchronous operations** — simulation does not synchronously depend on SCADA, GraphDB, or external clients.
8. **Source-generated events** — event provenance is preserved at the source.
9. **Traceability** — engineering, operational, simulation, fault, BOM, and AI results retain provenance.
10. **Temporal first-class design** — simulation time, wall time, run identity, and event time are explicit.
11. **Reproducibility** — deterministic configurations, random seeds, scenarios, and faults are recorded.
12. **Backend independence** — TEP is the first process backend, not the permanent boundary.
13. **AI-ready by design** — semantic and temporal foundations precede GraphRAG and agents.
14. **Template-first semantics** — authoritative submodel templates and semantic annotations precede KG lifting.
15. **Validation before integration** — structural and semantic constraints are validated before graph integration.
16. **Incremental implementation** — every increment should leave a usable, testable foundation.

## Repository structure

```text
process-sim/
├── README.md
├── requirements-opcua.txt
├── requirements-recording.txt
├── docs/
│   ├── opcua/
│   └── tep-reference/
├── examples/
│   ├── scenarios/
│   ├── record_tep_run.py
│   ├── inspect_tep_run.py
│   └── run_scenario.py
├── src/
│   └── process_sim/
│       ├── core/
│       ├── faults/
│       ├── opcua/
│       ├── recording/
│       ├── scenarios/
│       └── tep/
└── tests/
```

## Python code size

The current repository contains approximately **1,850 lines of Python** across the platform implementation, tests, and examples. This is an approximate source-size count and excludes the external ProfBraatz TEP reference package, documentation, YAML configuration, and generated run data.

| Area | Python LOC |
|---|---:|
| `src/process_sim/` | ~1,350 |
| `tests/` | ~315 |
| `examples/` | ~175 |
| **Total** | **~1,850** |

This number is an engineering-size indicator rather than a product metric and will change as the architecture becomes more complete.

## Guiding research principle

`process-sim` is intended to become more than a process simulator. The long-term research platform is built around a deliberate separation of responsibilities:

```text
Authoritative Models
        ↓
Submodel Templates
        ↓
Semantic Annotation
        ↓
Validation
        ↓
Semantic Lifting
        ↓
Canonical Identity
        ↓
Knowledge Graph
        ↓
Temporal Context
        ↓
Reasoning
        ↓
GraphRAG / Industrial AI
```

The scientific contribution should come from the **methods, representations, reasoning capabilities, and empirical evaluation**, not from repository size alone. `process-sim` provides the controlled simulation, fault, scenario, operational, and digital-thread environment needed to evaluate those ideas reproducibly.