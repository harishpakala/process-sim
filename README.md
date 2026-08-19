# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the reference process model and is designed to evolve into an industrial knowledge, temporal data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding industrial integration platform. The ProfBraatz TEP implementation is treated as the reference implementation; `process-sim` builds the Python interfaces, simulation orchestration, industrial integration, recording, semantic modeling, and AI foundations around it.

## Current status

**Phase 1 foundation + OPC UA integration + recording foundation**

The existing ProfBraatz `tep` package is used as the TEP backend through a `TEPAdapter`. OPC UA is implemented as a separate asynchronous integration boundary. A storage-neutral recording layer has now been added for process observations and discrete events.

Current OPC UA namespace:

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

Application namespace URI: `urn:process-sim:opcua`

The OPC UA server does not own the simulation clock. External writes are applied explicitly by the simulation orchestration layer so OPC UA remains an asynchronous integration boundary. The simulation can run at a configurable real-time factor while remaining independent of OPC UA clients.

### Recording foundation

`process-sim` now distinguishes between **continuous observations** and **discrete events**.

```text
Simulation
    │
    ├── Observations ──► recorder ──► time-series / Parquet
    │
    └── Events ────────► recorder ──► event log / Temporal KG
```

The initial `SimulationRecorder` is deliberately storage-neutral and currently keeps canonical records in memory. The canonical models are:

- `Observation` — timestamped process values such as XMEAS and XMV
- `Event` — semantically meaningful occurrences such as operator actions, faults, alarms, controller transitions, and simulation lifecycle changes
- `run_id` — identifies the simulation/experiment run
- `simulation_time_hours` — deterministic process time
- `wall_time` — real-world recording time when available
- `source` and provenance metadata

The recorder does **not** control or slow the simulation. Storage backends can be added later without changing the simulator API.

## Temporal data strategy

A central architectural decision is to **separate high-frequency time-series data from semantic temporal knowledge**.

A time-series store is the natural home for large volumes of numerical observations:

```text
XMEAS9 @ 120.0 h = 121.6
XMEAS9 @ 120.1 h = 121.7
XMEAS9 @ 120.2 h = 121.8
...
```

A Temporal Knowledge Graph is the natural home for entities, relationships, events, states, provenance, and temporal context:

```text
Operator
   │
   └── changed ──► XMV10
                       │
                       └── affects ──► Reactor Cooling
                                           │
                                           └── related to ──► Reactor Temperature
```

The Knowledge Graph should therefore **not become the historian**. High-frequency telemetry can remain in a dedicated time-series/data store, while the graph contains the semantic model, temporal events, metadata, relationships, and references to the underlying data.

For early experiments, Parquet is a suitable intermediate format because it is efficient, portable, and easy to analyze with Python. A production time-series database can be introduced after real workload and query patterns are understood.

### Observation vs event

Not every numerical change is an event.

```text
OBSERVATIONS
────────────────────────────────
123.0 h   XMV10 = 16.0
123.1 h   XMV10 = 16.2
123.2 h   XMV10 = 16.8
123.3 h   XMV10 = 17.4

EVENTS
────────────────────────────────
123.0 h   Operator changed XMV10: 16 → 20
125.4 h   Controller saturated
128.1 h   Reactor temperature alarm activated
131.7 h   Reactor temperature alarm cleared
```

Events are generated at the source of the occurrence rather than by repeatedly polling the graph. Examples include:

- simulation lifecycle events
- operator commands and setpoint changes
- manipulated-variable changes
- fault activation and clearance
- alarm activation and clearance
- operating-mode transitions
- controller mode/output-limit transitions
- process-derived events such as constraint violations
- communication and data-quality events

This event model provides the foundation for a future Temporal Knowledge Graph and causal/temporal analysis.

## Vision

The long-term goal is an **Industrial AI Platform** in which a semantic Industrial Knowledge Graph is the backbone connecting:

- process simulation
- plant and asset identity
- OPC UA and operational data
- SCADA/HMI
- time-series/historian data
- temporal events and states
- engineering information
- P&IDs and DEXPI
- ECAD and BIM/IFC
- ECLASS classifications
- BOM and enterprise information
- alarms, faults, maintenance, and procedures
- technical documents
- GraphRAG and AI agents

The central architectural principle is:

> Build the semantic and temporal foundation first, while keeping high-frequency telemetry in an appropriate data store and making simulation, SCADA, engineering, enterprise systems, and AI consume the same canonical plant model.

## Reference TEP implementation

The Tennessee Eastman Process implementation used as the scientific/reference baseline is:

- [jkitchin/tennessee-eastman-profbraatz](https://github.com/jkitchin/tennessee-eastman-profbraatz)
- Original upstream: [camaramm/tennessee-eastman-profBraatz](https://github.com/camaramm/tennessee-eastman-profBraatz)

The reference TEP implementation is **not reimplemented inside `process-sim`**. The platform wraps the existing simulator and preserves its scientific behavior.

## Development environment

The project is initially structured as an **Eclipse PyDev project**. Eclipse users can import the repository as an existing project and configure the Python interpreter/environment through PyDev.

The project uses a conventional Python `src/` layout so that it remains compatible with PyDev as well as modern Python tooling.

## Roadmap

### Phase 1 — TEP Reference and Python Simulation Integration

Establish a trustworthy process-simulation foundation.

- preserve the ProfBraatz implementation as the reference model
- define a clean Python simulator interface
- provide a TEP backend/adapter
- establish deterministic simulation control
- define simulation time and stepping semantics
- expose measurements and manipulated variables
- establish canonical observation and event models
- establish simulation run identity and provenance

### Phase 2 — Industrial Twin Core

Build the platform-independent orchestration layer.

- canonical plant and asset model
- equipment, instruments, tags, and functional relationships
- canonical identifiers
- source-system identifiers and provenance
- simulator abstraction
- deterministic simulation clock
- lifecycle and run management
- observation and event recording
- experiment metadata
- operating states and state transitions

The core must remain independent of TEP so that future process models can become additional backends.

### Phase 3 — Fault Injection and Scenario Engineering

Turn the simulator into a controlled industrial experimentation laboratory.

Supported fault concepts will include sensor bias, sensor drift, sensor noise, stuck sensors, actuator failure, actuator saturation, valve faults, process disturbances, parameter changes, controller faults, and communication faults.

Fault activation/clearance will generate explicit events so experiments can be reconstructed later in the temporal data layer.

### Phase 4 — OPC UA Integration

Expose the process simulation through an industrial interoperability layer.

The current implementation provides raw XMEAS/XMV variables, simulation state, a stable namespace, real-time-factor control, simulation lifecycle methods, and an explicit write bridge. Future additions will include semantic engineering names, units, quality/status/timestamps, subscriptions, process/equipment hierarchy, and fault/scenario controls.

The OPC UA layer remains separate from the simulator itself and must not synchronously own the deterministic simulation loop.

### Phase 5 — Time-Series and Temporal Knowledge Infrastructure

Introduce the two complementary data layers required by an industrial digital twin.

**Time-series/data layer:**

- high-frequency XMEAS/XMV and future sensor telemetry
- efficient range and trend queries
- historical experiment data
- Parquet as an early portable format
- production historian/time-series database selected from actual workload requirements

**Temporal Knowledge Graph:**

- plants, areas, units, equipment, instruments, and tags
- process topology and functional relationships
- temporal observations metadata
- events and state transitions
- alarms, faults, scenarios, and simulation runs
- provenance and source systems
- relationships between events, assets, measurements, and operating states
- references from semantic entities to underlying time-series data

GraphDB will be the semantic authority, while high-frequency telemetry remains in the appropriate data store.

### Phase 6 — Engineering and Digital Thread Integration

Connect P&ID, DEXPI, ECAD, BIM/IFC, CAD/3D, ECLASS, engineering documents, specifications, and datasheets to canonical plant identities.

### Phase 7 — BOM and Enterprise Integration

Support EBOM, MBOM, service/spare BOM, procurement relationships, revisions, quantities, lifecycle/status, manufacturer/supplier part numbers, ECLASS classifications, and ERP references.

### Phase 8 — Web SCADA / HMI

Build a web-based control-room experience on top of the canonical model, including plant mimic, telemetry, trends, alarms, controller faceplates, simulation controls, fault injection, scenarios, equipment hierarchy, documents, P&IDs, and BOM information.

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

1. **Reference-model integrity** — preserve the reference TEP behavior.
2. **Separation of concerns** — process physics, orchestration, industrial integration, data storage, visualization, and AI are separate layers.
3. **Canonical identity** — all systems map to the same plant/asset identities.
4. **Graph as semantic backbone** — the Knowledge Graph represents relationships, context, events, and temporal semantics rather than becoming a high-frequency telemetry database.
5. **Time-series where time-series belongs** — high-frequency numerical telemetry is stored in an efficient time-series/data layer.
6. **Observation/event separation** — continuous measurements are distinct from discrete, semantically meaningful occurrences.
7. **Asynchronous operations** — the deterministic simulation loop must not depend synchronously on SCADA, GraphDB, or external clients.
8. **Source-generated events** — events are emitted by the subsystem where they occur, preserving causality and provenance.
9. **Traceability** — engineering, operational, simulation, fault, BOM, and AI results retain provenance.
10. **Temporal first-class design** — simulation time, wall time, run identity, event time, and historical context are explicit concepts.
11. **Reproducibility** — simulations and fault scenarios are deterministic where possible and explicitly seed stochastic behavior.
12. **Backend independence** — TEP is the first process backend, not the permanent architectural boundary.
13. **AI-ready by design** — semantic and temporal foundations are built before adding GraphRAG and agents.
14. **Incremental implementation** — each phase should produce a usable, testable foundation for the next.

## Repository structure

```text
process-sim/
├── README.md
├── docs/
│   ├── opcua/
│   └── tep-reference/
├── src/
│   └── process_sim/
│       ├── core/
│       ├── backends/
│       │   └── tep/
│       ├── protocols/
│       │   └── opcua/
│       └── recording/
│           ├── models.py
│           └── recorder.py
└── tests/
```

See `docs/opcua/` for the OPC UA integration and `docs/tep-reference/` for the TEP reference documentation.
