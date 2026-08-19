# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Current status

**Phase 1 foundation complete; Phase 4 OPC UA initial integration complete; Phase 5 recording foundation implemented; Phase 3 fault injection foundation now implemented.**

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
- fault lifecycle events routable into the canonical recorder
- OPC UA operator XMV changes routable into the canonical event log

The implementation deliberately advances across phases where useful. The roadmap below describes the **target architecture and remaining work**, not a strict sequential implementation order.

## Current architecture

```text
                           process-sim
                                │
                ┌───────────────┼────────────────┐
                │               │                │
           TEPAdapter      FaultManager       OPC UA
                │               │                │
                └───────────────┼────────────────┘
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

## Fault injection foundation

The first FaultManager layer is now part of the platform core:

```text
FaultManager
    │
    ├── Bias
    ├── Drift
    ├── Stuck
    └── Process disturbance
```

Faults contain an ID, type, target, timing, magnitude/value, and metadata. They can be scheduled and queried by simulation time.

Signal-level faults currently operate at the TEP adapter boundary:

```text
TEP process model
       │
       ▼
   TEPAdapter
       │
       ▼
 FaultManager
   /       \
XMEAS      XMV
sensor    actuator
faults     faults
```

Process disturbances are intentionally kept separate from generic signal transformation. The next fault increment will connect scenario-managed process disturbances to native TEP IDVs.

Fault lifecycle events currently include:

```text
FaultActivated
FaultDeactivated
```

They can be recorded through the same canonical `Event` model used for simulation lifecycle and operator events.

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

## Temporal data strategy

High-frequency numerical telemetry belongs in a time-series/analytical data layer. Semantic relationships, events, states, provenance, and temporal context belong in the Temporal Knowledge Graph.

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

GraphDB should **not become the historian**. High-frequency telemetry remains in an efficient data store while the graph provides semantic context and references to underlying data.

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

## Roadmap

The project uses ten architectural phases. The phases are **not a rigid waterfall**.

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
- `FaultActivated` / `FaultDeactivated` events

Next:

- YAML/JSON scenario definitions
- scenario validation
- native TEP IDV process-disturbance integration
- noise and saturation faults
- actuator/sensor failure modes
- controller and communication faults
- scenario provenance and reproducible fault experiments

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
- native process-disturbance controls

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

Next:

- evaluate production TSDB/historian choices using real workload requirements
- temporal KG schema
- event/relationship model
- graph-to-time-series references
- quality/status/timestamp model
- retention and archival strategy

GraphDB remains the semantic authority and is not intended to store every 1-second numeric sample as RDF.

### Phase 6 — Engineering and Digital Thread Integration

Connect P&ID, DEXPI, ECAD, BIM/IFC, CAD/3D, ECLASS, engineering documents, specifications, and datasheets to canonical plant identities.

### Phase 7 — BOM and Enterprise Integration

Support EBOM, MBOM, service/spare BOM, procurement relationships, revisions, quantities, lifecycle/status, manufacturer/supplier part numbers, ECLASS classifications, and ERP references.

### Phase 8 — Web SCADA / HMI

Build a web control-room experience on the canonical model, including plant mimic, telemetry, trends, alarms, controller faceplates, simulation controls, fault injection, scenarios, equipment hierarchy, documents, P&IDs, and BOM information.

### Phase 9 — Knowledge, Documents, RAG and GraphRAG

Add document ingestion, metadata, chunking, embeddings, vector retrieval, graph retrieval, GraphRAG, evidence/provenance, procedures, and technical knowledge. Temporal operational context will be available alongside static engineering knowledge.

### Phase 10 — Industrial AI Platform

Build an AI assistant capable of reasoning over operational data, temporal events, process topology, alarms, faults, controllers, engineering relationships, maintenance history, BOM information, procedures, historical trends, and simulation results with traceable evidence.

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
14. **Incremental implementation** — every increment should leave a usable, testable foundation.

## Repository structure

```text
process-sim/
├── README.md
├── requirements-opcua.txt
├── requirements-recording.txt
├── docs/
│   ├── opcua/
│   │   └── README.md
│   └── tep-reference/
│       ├── README.md
│       └── USAGE.md
├── examples/
│   ├── record_tep_run.py
│   └── inspect_tep_run.py
├── src/
│   └── process_sim/
│       ├── core/
│       ├── backends/
│       │   └── tep/
│       ├── faults/
│       │   ├── models.py
│       │   └── manager.py
│       ├── protocols/
│       │   └── opcua/
│       └── recording/
│           ├── models.py
│           ├── recorder.py
│           ├── run.py
│           ├── parquet.py
│           └── session.py
└── tests/
```

See `docs/opcua/` for the OPC UA integration, `docs/tep-reference/` for the scientific/reference model, and `examples/` for the current recording workflow.
