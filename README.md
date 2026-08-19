# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, semantic modeling, and future AI foundations around it.

## Current status

**Phase 1 foundation complete; Phase 4 OPC UA integration implemented; Phase 5 recording foundation started.**

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
- Parquet persistence with one directory per simulation run
- recording and inspection examples

The implementation has deliberately started Phase 5 before all Phase 2/3 capabilities are complete. The roadmap below describes the **target architecture and remaining work**, not a strict sequential implementation order.

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

The current development server uses `opc.tcp://0.0.0.0:4841/process-sim/` because port 4840 was already occupied in the development environment.

OPC UA does not own the deterministic process clock. The server provides an asynchronous integration boundary, while simulation orchestration remains responsible for advancing the model.

## Recording foundation

`process-sim` separates **continuous observations** from **discrete semantic events**.

```text
Simulation
    │
    ├── Observations ──► SimulationRecorder ──► Parquet / future TSDB
    │
    └── Events ────────► SimulationRecorder ──► event log / future Temporal KG
```

Canonical records contain run identity, deterministic simulation time, wall-clock recording time, variable/event identity, value or event semantics, source, and provenance metadata.

`Observation` is used for values such as XMEAS and XMV. TEP XMEAS observations now carry engineering units from the reference mapping. XMV units remain unset until a sufficiently authoritative source is identified rather than inventing units.

`Event` is reserved for semantically meaningful occurrences such as operator actions, faults, alarms, controller transitions, and simulation lifecycle changes.

The recorder does not control or slow the simulator. It is intentionally pull-based in the current implementation: callers decide when to capture a snapshot.

## Recording a TEP run

Install the recording dependencies first:

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

Record less frequently, for example every 10 native steps:

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

The current Parquet layout is an **intermediate portable storage format**, not the final production historian architecture.

## Temporal data strategy

A central architectural decision is to separate high-frequency numerical telemetry from semantic temporal knowledge.

### Time-series/data layer

Use a time-series store or efficient analytical files for large volumes of numeric observations:

```text
XMEAS9 @ 120.0 h = 121.6 deg C
XMEAS9 @ 120.1 h = 121.7 deg C
XMEAS9 @ 120.2 h = 121.8 deg C
...
```

Parquet is the current portable format. A production TSDB/historian will be selected after actual workload and query requirements are understood.

### Temporal Knowledge Graph

Use the graph for entities, relationships, events, states, provenance, and temporal context:

```text
Operator
   │
   └── changed ──► XMV10
                       │
                       └── affects ──► Reactor Cooling
                                           │
                                           └── related to ──► Reactor Temperature
```

The Knowledge Graph should **not become the historian**. High-frequency telemetry remains in the appropriate data store, while the graph provides semantic context and references to the underlying data.

### Observation vs event

```text
OBSERVATIONS
123.0 h   XMV10 = 16.0
123.1 h   XMV10 = 16.2
123.2 h   XMV10 = 16.8

EVENTS
123.0 h   Operator changed XMV10: 16 → 20
125.4 h   Controller saturated
128.1 h   Reactor temperature alarm activated
```

Events should be generated by the subsystem where they occur, preserving causality and provenance, rather than inferred by repeatedly polling the graph.

## Roadmap

The project uses ten architectural phases. The phases are **not a rigid waterfall**; implementation can advance in one area while foundations in another are still being completed.

### Phase 1 — TEP Reference and Python Simulation Integration — FOUNDATION COMPLETE

- preserve ProfBraatz as the scientific reference
- define the simulator boundary
- provide the TEP adapter
- establish deterministic stepping and run identity
- expose measurements, manipulated variables, states, and disturbances
- establish canonical observations/events
- maintain TEP engineering mappings and measurement units

Remaining Phase 1 work is primarily deeper validation and reproducibility tooling.

### Phase 2 — Industrial Twin Core — IN PROGRESS / NEXT

Build the platform-independent orchestration layer:

- canonical plant and asset model
- equipment, instruments, tags, and functional relationships
- canonical identifiers and source-system identifiers
- deterministic simulation clock/orchestration
- lifecycle and run management
- experiment metadata
- operating states and state transitions
- event generation at source
- fault/scenario integration

The core must remain independent of TEP so future process models can become additional backends.

### Phase 3 — Fault Injection and Scenario Engineering — NEXT MAJOR CAPABILITY

Turn the simulator into a controlled industrial experimentation laboratory.

Planned fault types include sensor bias/drift/noise, stuck sensors, actuator failure and saturation, valve faults, process disturbances, parameter changes, controller faults, and communication faults.

Fault activation and clearance will generate explicit `FaultEvent` records and become part of scenario provenance.

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

Next OPC UA work:

- semantic engineering names alongside raw XMEAS/XMV names
- richer unit metadata and OPC UA EUInformation
- quality/status/timestamps
- subscriptions and client integration tests
- process/equipment hierarchy
- fault/scenario controls

### Phase 5 — Time-Series and Temporal Knowledge Infrastructure — STARTED

The recording foundation is implemented; the production data architecture remains ahead.

**Current:**

- canonical Observation/Event models
- run identity and provenance
- in-memory recorder
- Parquet storage
- TEP recording example
- observation units for XMEAS

**Next:**

- simulation lifecycle events such as `SimulationStarted` and `SimulationCompleted`
- richer event generation for operator/fault/controller actions
- run metadata and scenario manifests
- evaluate TSDB/historian choices using real workload requirements
- temporal KG schema and event/relationship model
- references between graph entities and time-series data

GraphDB remains the semantic authority; it is not intended to store every 1-second numeric sample as RDF.

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
11. **Reproducibility** — deterministic configurations and random seeds are recorded.
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
│       ├── protocols/
│       │   └── opcua/
│       └── recording/
│           ├── models.py
│           ├── recorder.py
│           ├── parquet.py
│           └── session.py
└── tests/
```

See `docs/opcua/` for the OPC UA integration, `docs/tep-reference/` for the scientific/reference model, and `examples/` for the current recording workflow.
