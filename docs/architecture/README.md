# process-sim: Four Architectural Pillars

The project has **10 detailed implementation phases**, but these phases are organized into **four higher-level architectural and research pillars**. The four-pillar view is intended for communicating the overall research program; the ten-phase roadmap remains the detailed engineering plan.

## The four pillars

### 1. Digital Twin & Simulation

**Detailed phases: 1–4**

The operational foundation:

- TEP scientific reference model
- backend-independent simulation interface
- industrial twin core
- deterministic runs and provenance
- fault injection and scenarios
- OPC UA / SCADA integration
- simulation lifecycle and operator interaction

This pillar provides the controlled, reproducible experimental environment.

### 2. Data & Temporal Infrastructure

**Detailed phase: 5**

The operational-data foundation:

- canonical observations and events
- Parquet / historical storage
- future time-series / historian integration
- temporal event model
- simulation and wall-clock provenance
- Temporal Knowledge Graph integration
- references between semantic context and numerical time-series data

High-frequency telemetry remains in an efficient time-series/analytical layer rather than becoming raw RDF in the KG.

### 3. Semantic Digital Thread

**Detailed phases: 6–7**

The semantic integration foundation:

- AAS Submodel Templates
- structural and cardinality constraints
- eCl@ss classification
- QUDT quantity kinds and units
- SHACL validation
- deterministic semantic lifting into OWL/RDF
- DEXPI / P&ID
- ECAD
- BOM / EBOM / MBOM / service BOM
- ERP and enterprise context
- canonical cross-domain identity
- provenance-preserving relationships

The central workflow is:

```text
Model
  ↓
Semantic Annotation
  ↓
Validation
  ↓
Semantic Lifting
  ↓
Cross-Domain Integration
  ↓
Reasoning
```

This pillar directly extends the semantic-lifting foundation established by the accepted ONTO:NEXUS workshop paper.

### 4. Industrial Intelligence

**Detailed phases: 8–10**

The intelligence layer:

- web SCADA / HMI
- operational dashboards and alarms
- document and procedure retrieval
- vector retrieval
- graph retrieval / GraphRAG
- temporal reasoning
- evidence and provenance
- industrial AI assistants and agents
- diagnosis, root-cause analysis, impact analysis, and maintenance reasoning

GraphRAG and AI are deliberately positioned **after** semantic modeling, validation, digital-thread integration, and temporal infrastructure.

## Relationship between the two roadmaps

```text
                    FOUR RESEARCH / ARCHITECTURE PILLARS

┌─────────────────────────────────────────────────────────────┐
│ 4. INDUSTRIAL INTELLIGENCE                                 │
│    Web SCADA · GraphRAG · Evidence · AI Agents             │
├─────────────────────────────────────────────────────────────┤
│ 3. SEMANTIC DIGITAL THREAD                                 │
│    AAS · eCl@ss · QUDT · SHACL · DEXPI · ECAD · BOM · ERP │
├─────────────────────────────────────────────────────────────┤
│ 2. DATA & TEMPORAL INFRASTRUCTURE                          │
│    Time-Series · Events · Provenance · Temporal KG         │
├─────────────────────────────────────────────────────────────┤
│ 1. DIGITAL TWIN & SIMULATION                               │
│    TEP · Twin Core · Faults · Scenarios · OPC UA           │
└─────────────────────────────────────────────────────────────┘

        ↓ detailed implementation ↓

1 TEP/Simulation
2 Twin Core
3 Faults/Scenarios
4 OPC UA
5 Temporal Data
6 Digital Thread
7 BOM/Enterprise
8 Web SCADA
9 GraphRAG
10 Industrial AI
```

The **10 phases should not be interpreted as a strict waterfall**. Work can advance across phases when a dependency or research question requires it. The four pillars provide the stable conceptual structure while the ten phases provide implementation-level tracking.

## Research progression

The intended research progression is:

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

This structure separates the **scientific/engineering infrastructure** from the eventual AI contribution. It also makes it possible to evaluate each added layer experimentally rather than claiming that a larger system is automatically a better research contribution.
