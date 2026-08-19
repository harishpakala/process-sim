# process-sim

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the reference process model and is designed to evolve into an industrial knowledge and AI platform.

The project deliberately separates the **reference process model** from the surrounding industrial integration platform. The ProfBraatz TEP Fortran implementation is treated as the reference implementation for validation; `process-sim` will build the Python interfaces, simulation orchestration, fault experimentation, OPC UA integration, knowledge graph, SCADA/HMI, engineering/BOM integration, and eventually GraphRAG/AI around it.

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

The original/reference Fortran implementation is **not replaced by or silently modified into the platform**. Python components in `process-sim` will be validated against known reference trajectories and behavior.

## Development environment

The project is initially structured as an **Eclipse PyDev project**. Eclipse users can import the repository as an existing project and configure the Python interpreter/environment through PyDev.

The project will use a conventional Python `src/` layout so that it remains compatible with PyDev as well as modern Python tooling.

## Roadmap

### Phase 1 — TEP Reference and Python Simulation Integration

Establish a trustworthy process-simulation foundation.

- preserve the ProfBraatz Fortran implementation as the reference model
- define a clean Python simulator interface
- provide a TEP backend/adapter
- establish deterministic simulation control
- define simulation time and stepping semantics
- expose measurements and manipulated variables
- build automated validation against reference trajectories
- establish reproducible simulation experiments

The objective is **not** to rewrite the process equations prematurely. The first priority is correctness and traceability.

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

Supported fault concepts will include:

- sensor bias
- sensor drift
- sensor noise
- stuck sensors
- actuator failure
- actuator saturation
- valve faults
- process disturbances
- parameter changes
- controller faults
- communication faults

Provide:

- fault definitions
- fault scheduling
- scenario files
- deterministic/random seeds
- active-fault tracking
- fault/event provenance
- reproducible datasets

A scenario should connect the fault to the resulting process trajectory, alarms, and observable symptoms.

### Phase 4 — OPC UA Integration

Expose the process simulation through an industrial interoperability layer.

The OPC UA layer will remain separate from the simulator itself.

Planned capabilities:

- stable OPC UA namespace
- process/equipment hierarchy
- measurements
- manipulated variables
- controller information
- engineering units
- timestamps and quality/status
- simulation controls
- fault/scenario controls
- subscriptions
- validated writes

The simulation loop must not depend synchronously on OPC UA clients.

Conceptually:

```text
TEP reference/model
       |
       v
Python simulator adapter
       |
       v
Industrial Twin Core
       |
       v
OPC UA Server
       |
       v
SCADA / HMI / external clients
```

### Phase 5 — Industrial Knowledge Graph with GraphDB

Introduce the semantic backbone of the platform.

The Knowledge Graph will represent:

- plants
- areas and units
- equipment
- instruments
- tags
- process topology
- measurements
- alarms
- events
- faults
- scenarios
- simulation models
- documents
- procedures
- provenance

GraphDB will be the semantic authority, while high-frequency telemetry may remain in a dedicated time-series/data store with references and metadata represented in the graph.

The graph will also map semantic assets to OPC UA nodes and simulation variables.

Example:

```text
Reactor R-101
   |
   +-- hasMeasurement --> TT-101
   |                         |
   |                         +-- opcuaNode --> ns=...;s=TT-101
   |
   +-- hasComponent --> Valve XV-104
   |
   +-- documentedBy --> P&ID
   |
   +-- simulatedBy --> TEP model
```

### Phase 6 — Engineering and Digital Thread Integration

Connect engineering systems to the canonical asset model.

Planned integration areas:

- P&ID
- DEXPI
- ECAD
- BIM/IFC
- CAD/3D information
- ECLASS
- engineering documents
- specifications and datasheets

The Knowledge Graph will establish canonical identity and relationships between representations from different source systems.

For example, one canonical reactor identity may link its:

- DEXPI/P&ID representation
- BIM representation
- ECAD relationships
- ECLASS classification
- ERP identifier
- OPC UA nodes
- TEP representation
- future DWSIM representation

### Phase 7 — BOM and Enterprise Integration

BOM is a first-class part of the digital thread.

Support will include:

- Engineering BOM (EBOM)
- Manufacturing/assembly BOM (MBOM)
- service/spare BOM
- procurement relationships
- BOM revisions
- item positions
- quantities
- lifecycle/status
- manufacturer and supplier part numbers
- ECLASS classifications
- ERP asset and material references

The Knowledge Graph will connect BOM components to the physical/functional assets on which they are installed.

Example:

```text
BOM-1001
   |
   +-- assembly --> R-101
   +-- revision --> C
   +-- item --> TT-101
   +-- item --> PT-101
   +-- item --> XV-104
```

### Phase 8 — Web SCADA / HMI

Build a web-based control-room experience on top of the canonical model.

Planned functions:

- plant overview/process mimic
- live telemetry
- trends
- alarms
- controller faceplates
- simulation controls
- fault injection
- scenario management
- equipment hierarchy
- engineering documents
- P&ID navigation
- BOM information
- asset context

The HMI should be **schema/KG-driven rather than maintaining a separate hard-coded plant model**.

A typical equipment faceplate will eventually combine:

```text
R-101

LIVE
  Temperature / Pressure / Level

ENGINEERING
  P&ID / Datasheet / BIM / ECAD / DEXPI

BOM
  Components / Revision / Status

OPERATIONS
  Alarms / Trends / Maintenance

SIMULATION
  TEP model / Scenarios / Faults

ENTERPRISE
  ERP asset / ECLASS
```

### Phase 9 — Knowledge, Documents, RAG and GraphRAG

Add the knowledge layer above the Industrial Knowledge Graph.

Components will include:

- document ingestion
- document metadata
- chunking
- embeddings
- vector retrieval
- graph retrieval
- GraphRAG
- context fusion
- evidence/provenance
- procedures and technical knowledge

The distinction is important:

- **GraphDB:** What is related to this asset?
- **Operational data:** What is happening now?
- **Documents/vector retrieval:** What do the manuals and procedures say?
- **AI:** How do these pieces of evidence combine to answer the question?

### Phase 10 — Industrial AI Platform

The final layer is an AI assistant capable of reasoning over the complete industrial digital thread.

Example question:

> Why is reactor R-101 temperature increasing?

The system should be able to combine:

- current measurements
- process topology
- active alarms
- active faults
- controller state
- engineering relationships
- maintenance history
- BOM/component information
- procedures
- historical trends
- simulation results

The AI should provide **traceable answers backed by evidence**, rather than unsupported conclusions.

Eventually the AI may perform contextual actions such as:

- show an equipment faceplate
- open the relevant P&ID
- display a trend before/after an event
- identify affected BOM components
- retrieve the applicable procedure
- run a corresponding simulation scenario
- compare simulated and observed behavior

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

1. **Reference-model integrity** — preserve the reference TEP behavior and validate integrations against it.
2. **Separation of concerns** — process physics, industrial integration, visualization, and AI are separate layers.
3. **Canonical identity** — all systems map to the same plant/asset identities.
4. **Graph as semantic backbone** — GraphDB represents relationships and context rather than becoming a high-frequency telemetry database.
5. **Asynchronous operations** — the deterministic simulation loop must not depend synchronously on SCADA, GraphDB, or external clients.
6. **Traceability** — engineering, operational, simulation, fault, BOM, and AI results should retain provenance.
7. **Reproducibility** — simulations and fault scenarios should be deterministic where possible and explicitly seed stochastic behavior.
8. **Backend independence** — TEP is the first process backend, not the permanent architectural boundary.
9. **AI-ready by design** — the semantic model is built before adding GraphRAG and agents.
10. **Incremental implementation** — each phase should produce a usable, testable foundation for the next.

## Initial repository structure

```text
process-sim/
├── README.md
├── .project
├── .pydevproject
├── .gitignore
├── src/
│   └── process_sim/
│       └── __init__.py
└── tests/
    └── __init__.py
```

This initial commit intentionally contains only the project foundation and roadmap. The original/reference TEP implementation is not copied into this repository at this stage.

## Status

**Project initialization — Phase 1 planning**

The next implementation step is to inspect the reference Fortran TEP implementation in detail and define the Python simulator interface and validation strategy before adding OPC UA or the Knowledge Graph.
