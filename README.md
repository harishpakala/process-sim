# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the reference process model and is designed to evolve into an industrial knowledge and AI platform.

The project deliberately separates the **reference process model** from the surrounding industrial integration platform. The ProfBraatz TEP implementation is treated as the reference implementation; `process-sim` builds the Python interfaces and industrial integration around it.

## Current status

**Phase 1 foundation + initial OPC UA integration**

The existing ProfBraatz `tep` package is used as the TEP backend through a thin `TEPAdapter`. The first OPC UA adapter is now being built separately from the simulator and exposes the raw TEP interface through a stable application namespace.

Current OPC UA namespace:

```text
Objects
└── TEP
    ├── Simulation
    │   ├── TimeHours
    │   └── Running
    ├── Measurements
    │   └── XMEAS1 ... XMEAS41
    └── ManipulatedVariables
        └── XMV1 ... XMV12
```

Application namespace URI: `urn:process-sim:opcua`

The OPC UA server does not own the simulation clock. External writes are applied explicitly by the simulation orchestration layer so OPC UA remains an asynchronous integration boundary.

## Vision

The long-term goal is an **Industrial AI Platform** in which a semantic Industrial Knowledge Graph is the backbone connecting:

- process simulation
- plant and asset identity
- OPC UA and operational data
- SCADA/HMI
- engineering information
- P&IDs and DEXPI
- ECAD and BIM/IFC
- ECLASS classifications
- BOM and enterprise information
- alarms, events, maintenance, and faults
- procedures and technical documents
- GraphRAG and AI agents

The central architectural principle is:

> Build the semantic foundation first, and make simulation, SCADA, engineering, enterprise systems, and AI consume the same canonical plant model.

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

### Phase 2 — Industrial Twin Core

Build the platform-independent orchestration layer.

- canonical plant and asset model
- equipment, instruments, tags, and functional relationships
- canonical identifiers
- source-system identifiers and provenance
- simulator abstraction
- simulation clock
- lifecycle and run management
- events and timestamps
- configuration and experiment metadata

The core must remain independent of TEP so that future process models can become additional backends.

### Phase 3 — Fault Injection and Scenario Engineering

Turn the simulator into a controlled industrial experimentation laboratory.

Supported fault concepts will include sensor bias, sensor drift, sensor noise, stuck sensors, actuator failure, actuator saturation, valve faults, process disturbances, parameter changes, controller faults, and communication faults.

### Phase 4 — OPC UA Integration

Expose the process simulation through an industrial interoperability layer.

The first implementation is deliberately small: raw XMEAS/XMV variables, simulation state, stable namespace, and an explicit write bridge. Future additions will include semantic engineering names, units, quality/status/timestamps, subscriptions, simulation controls, fault/scenario controls, and process/equipment hierarchy.

The OPC UA layer remains separate from the simulator itself and must not synchronously own the deterministic simulation loop.

### Phase 5 — Industrial Knowledge Graph with GraphDB

Introduce the semantic backbone of the platform.

The Knowledge Graph will represent plants, areas and units, equipment, instruments, tags, process topology, measurements, alarms, events, faults, scenarios, simulation models, documents, procedures, and provenance.

GraphDB will be the semantic authority, while high-frequency telemetry may remain in a dedicated time-series/data store with references and metadata represented in the graph.

### Phase 6 — Engineering and Digital Thread Integration

Connect P&ID, DEXPI, ECAD, BIM/IFC, CAD/3D, ECLASS, engineering documents, specifications, and datasheets to canonical plant identities.

### Phase 7 — BOM and Enterprise Integration

Support EBOM, MBOM, service/spare BOM, procurement relationships, revisions, quantities, lifecycle/status, manufacturer/supplier part numbers, ECLASS classifications, and ERP references.

### Phase 8 — Web SCADA / HMI

Build a web-based control-room experience on top of the canonical model, including plant mimic, telemetry, trends, alarms, controller faceplates, simulation controls, fault injection, scenarios, equipment hierarchy, documents, P&IDs, and BOM information.

### Phase 9 — Knowledge, Documents, RAG and GraphRAG

Add document ingestion, metadata, chunking, embeddings, vector retrieval, graph retrieval, GraphRAG, evidence/provenance, procedures, and technical knowledge.

### Phase 10 — Industrial AI Platform

Build an AI assistant capable of reasoning over operational data, process topology, alarms, faults, controllers, engineering relationships, maintenance history, BOM information, procedures, historical trends, and simulation results with traceable evidence.

## Target architecture

```text
                         User / Operator
                                |
                                v
                         AI Copilot / AI
                                |
                    +-----------+-----------+
                    |                       |
               Graph Retrieval        Vector Retrieval
                    |                       |
                    v                       v
              GraphDB / KG          Document Store
                    |                       |
                    +-----------+-----------+
                                |
                         Context Fusion
                                |
                                v
                              LLM
                                |
              +-----------------+------------------+
              |                                    |
        Industrial Twin                      SCADA / HMI
              |
       +------+-------+----------------+
       |              |                |
      TEP          OPC UA          Engineering
       |              |                |
       |              |          DEXPI / ECAD / BIM
       |              |                |
       +--------------+----------------+
                      |
                 Asset Identity
                      |
                 BOM / Enterprise
```

## Design principles

1. **Reference-model integrity** — preserve the reference TEP behavior.
2. **Separation of concerns** — process physics, industrial integration, visualization, and AI are separate layers.
3. **Canonical identity** — all systems map to the same plant/asset identities.
4. **Graph as semantic backbone** — GraphDB represents relationships and context rather than becoming a high-frequency telemetry database.
5. **Asynchronous operations** — the deterministic simulation loop must not depend synchronously on SCADA, GraphDB, or external clients.
6. **Traceability** — engineering, operational, simulation, fault, BOM, and AI results retain provenance.
7. **Reproducibility** — simulations and fault scenarios are deterministic where possible and explicitly seed stochastic behavior.
8. **Backend independence** — TEP is the first process backend, not the permanent architectural boundary.
9. **AI-ready by design** — the semantic model is built before adding GraphRAG and agents.
10. **Incremental implementation** — each phase should produce a usable, testable foundation for the next.

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
│       └── protocols/
│           └── opcua/
└── tests/
```

See `docs/opcua/README.md` for the initial OPC UA integration and `docs/tep-reference/` for the TEP reference documentation.
