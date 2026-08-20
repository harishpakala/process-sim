# process-sim: Four Architectural Pillars

The project has **10 detailed implementation phases**, organized into **four higher-level architectural and research pillars**. The four-pillar view communicates the research program; the ten-phase roadmap remains the detailed engineering plan.

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

### 2. Data & Temporal Infrastructure

**Detailed phase: 5**

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

### 4. Industrial Intelligence

**Detailed phases: 8–10**

- web SCADA / HMI
- operational dashboards and alarms
- document and procedure retrieval
- vector retrieval
- graph retrieval / GraphRAG
- temporal reasoning
- evidence and provenance
- industrial AI assistants and agents
- diagnosis, root-cause analysis, impact analysis, and maintenance reasoning

GraphRAG and AI are deliberately positioned after semantic modeling, validation, digital-thread integration, and temporal infrastructure.

## Automation-pyramid operational architecture

The operational interface follows an industrial automation-pyramid concept. The SCADA/HMI is an operational consumer of the process interface; it should not directly call simulator internals.

```text
┌──────────────────────────────────────────────────────┐
│                    SCADA / HMI                       │
│  Process overview · Trends · Alarms · Operator UI   │
│  Start/Stop/Reset · Fault Injection                 │
└─────────────────────────┬────────────────────────────┘
                          │ OPC UA
                          ▼
┌──────────────────────────────────────────────────────┐
│               OPC UA Operational Layer               │
│  Process variables · Commands · Events · Alarms     │
│  Fault-management interface · Operator actions      │
└─────────────────────────┬────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│             Controller / Control-System Layer        │
│  PID / cascade control · Interlocks · Control logic │
└─────────────────────────┬────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│                Process / Digital Twin                │
│  Tennessee Eastman Process · Sensors · Actuators    │
│  Dynamics · Fault behavior                           │
└─────────────────────────┬────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│             Historian / Temporal Data               │
│  Observations · Events · Fault lifecycle            │
│  Operator actions · Provenance                       │
└──────────────────────────────────────────────────────┘
```

The intended operational fault path is:

```text
SCADA/HMI
    │
    │ OPC UA command
    ▼
Fault Management
    │
    ▼
TEPAdapter
    │
    ▼
Tennessee Eastman Process
    │
    ├──────────────► Observations
    └──────────────► Events / provenance
```

Fault injection through the SCADA/HMI is a **planned operational capability**. It is distinct from declarative experiment/scenario execution: the scenario path provides controlled, reproducible benchmark experiments, while the OPC UA path represents operator-facing operational interaction with the digital twin.

## OPC UA operational contract

The current OPC UA implementation provides the initial operational interface:

- stable application namespace
- TEP process object
- 41 XMEAS measurement nodes
- 12 XMV manipulated-variable nodes
- simulation time and running state
- Start/Stop/Reset methods
- configurable real-time factor
- XMV write bridge
- asynchronous simulation loop
- operator XMV event integration

Current endpoint:

```text
opc.tcp://0.0.0.0:4841/process-sim/
```

Port `4841` is used because `4840` was occupied in the development environment. It is the current process-sim configuration, not a universal industrial deployment default.

The next OPC UA layer will establish a stable contract for:

- semantic engineering names and units
- EUInformation and quality/status/timestamps
- alarms and events
- operator actions
- controlled fault injection and fault clearing
- external SCADA/HMI integration tests
- security and deployment configuration

The HMI should consume this contract over OPC UA rather than calling Python simulator APIs directly.

## Fault entry paths

The long-term architecture has two complementary fault entry paths:

```text
Declarative experiment path                 Operational path

Scenario YAML / JSON                        SCADA / HMI
        │                                       │
        ▼                                       │ OPC UA
ScenarioRunner                                 ▼
        │                                  OPC UA layer
        ▼                                       │
FaultManager ◄─────────────────────────────────┘
        │
        ▼
TEPAdapter
        │
        ▼
TEP process model
        │
        ├──► observations
        └──► events / provenance
```

The declarative path is authoritative for reproducible benchmark design. The operational path is intended to reproduce realistic operator interaction while preserving fault identity, simulation timestamps, lifecycle events, and provenance.

## Relationship between the roadmaps

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

The **10 phases are not a strict waterfall**. Work can advance across phases when a dependency or research question requires it.

## Research progression

```text
Controlled Digital Twin
        ↓
Reproducible Operational Data
        ↓
OPC UA Operational Interface
        ↓
SCADA/HMI + Fault Injection
        ↓
Semantically Integrated Digital Thread
        ↓
Temporal + Engineering Reasoning
        ↓
Evidence-Grounded Industrial AI
```

This structure separates scientific/engineering infrastructure from the eventual AI contribution and makes it possible to evaluate each added layer experimentally rather than assuming that a larger system is automatically a better research contribution.
