# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Current development milestone — Semantic Digital Thread prototype (October 2026)

The active integration milestone is **Phase 6 — Engineering & Semantic Digital Thread**, with early user-interface work from Phases 8 and 9. This is a prototype milestone, **not** completion of the full semantic digital thread or the GraphRAG phase.

| Phase | Roadmap status | Implemented in the current milestone | Still required |
|---|---|---|---|
| 1 — TEP reference integration | Foundation complete | TEP adapter, deterministic simulation boundary, engineering measurements | Ongoing maintenance |
| 2 — Industrial twin core | In progress | Simulation lifecycle and run context | Canonical cross-domain plant/asset model, operating-state semantics |
| 3 — Faults and scenarios | Foundation implemented | Fault manager, scenarios, lifecycle events and native disturbances | Extended fault families, schema validation and comparisons |
| 4 — OPC UA | Fault-management foundation complete | Simulation controls, XMEAS/XMV and fault-management methods | OPC UA events, security, engineering metadata and external HMI verification |
| 5 — Temporal data and experiments | Experiment foundation implemented | Parquet recording, provenance, controlled experiments, replication and sweeps | Historian/TSDB, temporal KG and expanded benchmarks |
| **6 — Engineering & Semantic Digital Thread** | **Prototype implemented; integration/validation in progress** | AAS templates and example instances for DEXPI, ECAD and ProductCatalog; configurable RDF template/instance lifting scripts; ProductCatalog engineering audit | RDF-level completeness audit and repeatable CI validation; GraphDB ingestion; cross-domain identity and provenance; QUDT/eCl@ss enrichment |
| 7 — BOM and enterprise | Planned | ProductCatalog manufacturer/part-number source data is a preliminary input | Enterprise master data, EBOM/MBOM, ERP integration and identity resolution |
| **8 — Web SCADA / HMI** | **Frontend prototype; operational integration pending** | TEP NEXUS Vue/Vite navigation and engineering ProductCatalog explorer | Live OPC UA-backed SCADA, trends, alarms, authenticated operational actions |
| **9 — Knowledge Graph & GraphRAG** | **Graph visualization prototype only** | GraphDB-style ProductCatalog explorer with labeled AAS-derived relationships, pan/zoom, node dragging, expansion and node-property side pane | Live RDF/SPARQL query API, actual ontology predicates, cross-domain KG, reasoning and GraphRAG |
| 10 — Industrial AI | Planned | No production agent or industrial AI capabilities established | Agent architecture, evidence-backed recommendations, safety and benchmark evaluation |

### Semantic lifting and validation status (October 2026)

The four configured AAS template/instance pairs are lifted using `scripts/import_knowledge_graph.py` and the paths in [`semantic/config.py`](semantic/config.py). In particular, ECAD validation uses [`semantic/templates/ecad_template.json`](semantic/templates/ecad_template.json), **not** the separate `examples/aas/ecad_template.json` file. Template cardinalities are converted to SHACL shapes; instance `ontoConcept` qualifiers determine semantic RDF classes and collection predicates while instance `idShort` values preserve element identity.

A local run reported **`Conforms: True` for all four domains**, with the following output. These triple counts document that reported run and are not asserted to be the counts for every later revision.

| Domain | Template triples | Instance triples | SHACL result |
|---|---:|---:|---|
| DEXPI | 134 | 638 | Conforms: True |
| ECAD | 227 | 96 | Conforms: True |
| ProductCatalog | 95 | 422 | Conforms: True |
| AssetInventory | 136 | 3,270 | Conforms: True |

**Important:** The 96-triple ECAD result was produced before the larger ECAD dataset was restored. The user subsequently reported successful validation after the restoration, but the new full-instance RDF triple count has not been recorded here. Do not use 96 as the expected size of the current ECAD RDF graph.

The current ECAD AAS source contains **40 devices**, **100 standard `EndPoint` collections**, **40 PLC `PLCEndPoint` collections**, **102 schematic relationships**, and **2 electrical nets**. Only `PLCBox` uses `PLCEndPoint`; other devices use `EndPoint`. Both endpoint types are declared `ZeroToMany` in the active ECAD template. The `ElectricalNets` collection is retained in the ECAD instance even though it is not defined in the active ECAD template; SHACL conformance alone does not certify that every source collection is modeled by a shape.

Source-JSON consistency checks also found:

- All **102** ECAD schematic relationship endpoints resolve to existing ECAD instance elements.
- All **38 of 38** ECAD devices with manufacturer part numbers match a ProductCatalog part number.
- All **5 of 5** AssetInventory `EngineeringReference` values checked match DEXPI `AssetIdentifier` values.
- The DEXPI source includes **5 equipment**, **22 instrumentation functions**, and **12 actuating functions**. ProductCatalog contains **8 products**, and AssetInventory contains **62 assets**.

These are **source-level checks**, not proof that every AAS element or every cross-domain relationship is represented in the lifted RDF. RDF-level completeness (including all 140 ECAD endpoints and 102 connections), explicit cross-domain RDF links, GraphDB ingestion, and provenance remain outstanding verification work.

To regenerate and validate locally:

```bash
python3 scripts/import_knowledge_graph.py --validate
```

The script writes domain-specific template and instance Turtle files to `out/semantic/`; add `--push` only when GraphDB publication is intended.

### What the ProductCatalog UI demonstrates

The existing **Technical details** view remains a searchable **local AAS JSON snapshot** with manufacturer filtering, product identifiers, technical properties and documentation links. Its **Knowledge graph** tab provides a GraphDB-style interactive **preview derived from that same JSON**. Resource links are rendered as edges; scalar fields such as `hasAssetIdentifier` appear in a selected-node properties pane. The graph supports wheel zoom, drag-to-pan, draggable nodes and fit-to-screen.

**Important evidence boundary:** The graph is not connected to GraphDB, does not execute SPARQL and does not display verified lifted RDF predicates. The semantic lifting scripts are present, but their existence alone does not establish successful RDF/SHACL/GraphDB integration or browser-tested operation.

Run the frontend from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Run the semantic lifting entry points separately with Python 3.12 and the required dependencies:

```bash
python3.12 -m semantic.template_lifting
python3.12 -m semantic.instance_lifting
```

By default, these generate local Turtle files in `out/semantic/`; validation and GraphDB upload require explicit `--validate` and `--push` flags. See [semantic/README.md](semantic/README.md) and [frontend/README.md](frontend/README.md).

### Next acceptance milestones

1. Automate four-domain RDF/SHACL validation in CI and audit RDF lifting completeness against the source AAS instances.
2. Establish GraphDB repository ingestion and SPARQL queries, then replace the AAS-derived graph preview with verified RDF nodes and predicates.
3. Establish stable identifiers and provenance linking ProductCatalog, DEXPI and ECAD.
4. Integrate the UI with live industrial/operational services and add frontend build, interaction and integration tests.

## TEP NEXUS — ECLASS equipment classification reference (October 2026)

This is the **working classification register** for physical equipment in the Tennessee Eastman Process (TEP) semantic digital twin. The ECLASS names and IRDIs below were supplied from ECLASS lookup during engineering review. They describe **physical product/asset types**, not XMEAS measurements or XMV manipulated-variable identifiers. These selections are design decisions for TEP NEXUS, **not claims that the original TEP simulation specifies particular commercial hardware**.

| Physical equipment / asset | ECLASS class | Preferred name | ECLASS class IRDI | Decision / qualification |
|---|---|---|---|---|
| Process control valves (11 physical valves) | 37-01-02-03 | Control globe valve | `0173-1#01-AAD651#023` | Selected; explicitly assumes globe-valve construction |
| Temperature sensors | 27-27-51 | Temperature sensor | `0173-1#01-AHB186#005` | Selected; electrical temperature sensor assumed |
| Pressure sensors | 27-27-49 | Pressure sensor | `0173-1#01-AHB184#005` | Selected |
| Level transmitters | 27-20-05 | Level gauge or transmitter | `0173-1#01-AAC020#014` | Selected; transmitter implementation assumed |
| Reactor | 36-02-01 | Reactor | `0173-1#01-AAD319#012` | Selected |
| Process pumps | 36-41 | Pump | `0173-1#01-AAD563#010` | Selected; not applicable to compressor |
| Condenser | 36-04 | Heat exchanger | `0173-1#01-AAD338#010` | Selected broad class |
| Gas–liquid separator | 36-20-17-04 | Vessel separator (for gases) | `0173-1#01-AKL760#020` | Selected; assumes a vessel-type gas–liquid separator, without specifying internals |
| Stripper | 36-01-01 | Column | `0173-1#01-AAD304#013` | Selected broad industrial column class |
| Reactor agitator assembly | 36-09-08-01 | Agitator (complete) | `0173-1#01-AKP267#021` | Selected; assembly may include motor unless motor is modeled separately |
| Separately modeled pump, compressor, and agitator drive motors | 27-02-24 | Synchronous motor | `0173-1#01-AKE158#012` | Selected as an explicit motor-technology assumption |
| Recycle gas compressor | 36-43 | Compressor, ventilator, vacuum pump | `0173-1#01-AAD585#011` | Selected broad parent class; verify product-class assignability in the ECLASS version in use |

### Classification rules and evidence boundaries

- **ProductCatalog AAS** should hold the authoritative ECLASS classification for a product type; **AssetInventory AAS** should reference that product for each installed asset. Validate actual inventory coverage before claiming every physical asset is classified.
- Each `0173-1#01-...#...` identifier above is an **ECLASS class IRDI**. Do not reuse it as the semantic ID of an unrelated AAS property such as `DeviceType`.
- Classify the **driven machine** and its **electric motor** separately only where the motor is represented as a distinct asset. The agitator's *complete* assembly classification must not be confused with the standalone motor classification.
- The recycle compressor's broad 36-43 class avoids an unsupported assumption about rotary positive displacement, reciprocating compression, or turbo compression. **Confirm whether the parent class is directly assignable** in the selected ECLASS release before implementing the ProductCatalog mapping.
- The gas–liquid separator selection assumes a **vessel separator**. The TEP process model does not specify separator internals.
- The eleven globe-valve selections and the synchronous-motor selection are **TEP NEXUS modeling assumptions** rather than verified original TEP equipment specifications. XMV(12) denotes agitator speed control, **not a twelfth physical control valve**.
- Synchronous motors require appropriate electrical drive arrangements. A 24 V DC instrumentation supply does **not** by itself establish suitable motor power or drive compatibility. ECAD power distribution and motor-drive details remain a separate consistency review.
- No ECLASS classifications have been written into ProductCatalog or AssetInventory AAS instances merely by documenting this register.

### Reviewed alternatives not selected

- **Linear DC motor** (`0173-1#01-ADJ119#015`) and **Linear induction motor** (`0173-1#01-ADJ117#015`): linear rather than rotary motion.
- **Universal motor** (`0173-1#01-AKE157#019`): rotary, but not the selected continuous industrial-drive technology.
- **Electric motor (motor vehicle)** (`0173-1#01-AFX525#006`) and **Motor (hydraulics, other)** (`0173-1#01-AGU935#004`): incorrect application domain or energy-conversion technology.
- **Submersible motor pump** (`0173-1#01-AKL848#022`): assumes submerged pump construction and describes a pump unit rather than a standalone drive motor.
- **Compressor (positive type, rotating)** (`0173-1#01-AAD586#013`), **Compressor (special execution)** (`0173-1#01-AAD589#012`), and **Compressor, ventilator, vacuum pump (other)** (`0173-1#01-AKL925#012`): not selected without evidence of the specified design or an actual *other* subtype.

**Next implementation step:** reconcile this reference with the actual ProductCatalog and AssetInventory records, verify assignability of parent ECLASS classes, then add classifications to the authoritative AAS product data. Keep ECAD electrical topology changes separate from this documentation step.

## Current status

The implementation currently spans the simulation, fault/scenario, OPC UA, recording, and controlled-experiment foundations. The complete roadmap contains 10 phases organized under four architectural pillars.

Implemented and verified at the platform level:

- ProfBraatz TEP exposed through `TEPAdapter`
- backend-independent `ProcessSimulator` boundary
- deterministic seeded TEP simulation control
- 41 XMEAS measurements, 12 XMV manipulated variables, and 20 IDV disturbance slots
- authoritative XMEAS engineering units
- asynchronous OPC UA integration
- simulation lifecycle controls and configurable real-time factor
- OPC UA XMEAS/XMV exposure and XMV write bridge
- OPC UA fault-management contract: `InjectFault`, `ClearFault`, `ClearAllFaults`, and `ListFaults`
- operator fault provenance through OPC UA metadata
- fault lifecycle status reporting: `registered`, `active`, and `expired`
- fault lifecycle events including `FaultInjected`, `FaultActivated`, `FaultDeactivated`, and `FaultCleared` in the platform event path
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
- declarative `Experiment` / `GroundTruth` models and `ExperimentRunner`
- experiment provenance persisted in run metadata
- paired fault/baseline replication runner
- fault-magnitude sweep tooling with RMSE, MAE, peak error, IAE, and ISE metrics
- initial controlled benchmark fixtures and reproducibility evidence

## OPC UA and industrial automation architecture

The operational integration follows an industrial automation-pyramid concept. The SCADA/HMI layer is intended to interact with the process through OPC UA rather than calling simulator internals directly.

```text
SCADA / HMI
     │
     │ OPC UA
     ▼
OPC UA operational layer
     │
     ├── Simulation lifecycle
     ├── Measurements / manipulated variables
     └── Fault management
     │
     ▼
Controller / control system
     │
     ▼
TEP process / digital twin
     │
     ├──────────────► Observations
     │
     └──────────────► Events / provenance
                              │
                              ▼
                    Parquet / future historian
```

Current endpoint:

```text
opc.tcp://0.0.0.0:4841/process-sim/
```

Port `4841` is the current application configuration because the conventional OPC UA port `4840` was already occupied in the development environment. Deployment configuration may choose another available port.

### Current OPC UA contract

```text
TEP
├── Simulation
│   ├── TimeHours
│   ├── Running
│   ├── RealTimeFactor
│   ├── Start()
│   ├── Stop()
│   └── Reset()
├── FaultManagement
│   ├── FaultCount
│   ├── InjectFault(...)
│   ├── ClearFault(faultId)
│   ├── ClearAllFaults()
│   └── ListFaults()
├── Measurements
│   └── XMEAS1 ... XMEAS41
└── ManipulatedVariables
    └── XMV1 ... XMV12
```

An OPC UA fault injection carries fault identity, type, target, magnitude/value, duration, and operator provenance. Faults remain registered after expiry so that lifecycle information remains queryable rather than being silently deleted.

Example lifecycle:

```text
registered
    │ start time reached
    ▼
active
    │ duration elapsed
    ▼
expired
```

For an indefinite fault, the status remains `active` until the operator explicitly clears it.

The declarative scenario/experiment path remains the authoritative path for reproducible scientific benchmarks. OPC UA fault injection is the operator-facing operational path. Both paths feed the same fault-management and provenance model.

## First controlled experiment

Experiment `reactor_cooling_bias_001` was executed end-to-end and inspected successfully before the controller-path correction. It established the deterministic execution and temporal ground-truth layer:

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

The recorded lifecycle was:

```text
0.0 h   SimulationStarted
1.0 h   FaultActivated     XMEAS9
1.5 h   FaultDeactivated   XMEAS9
2.0 h   SimulationCompleted
```

This established reproducible experiment configuration, persisted ground truth, exact temporal fault boundaries, complete observation coverage, and run provenance. It did **not** establish closed-loop process propagation because the scheduled sensor fault was initially applied only to the recorded measurement path.

## Closed-loop fault propagation benchmark

The controller path was subsequently corrected so scheduled sensor faults are injected into the native TEP controller measurement input before controller calculations, while the same fault remains visible in recorded observations.

The relevant control relationship is:

```text
XMEAS9 reactor-temperature measurement
        │
        ▼
Controller 18
        │
        ▼
reactor-temperature cascade setpoint
        │
        ▼
Controller 10
        │
        ▼
XMV10 reactor cooling-water flow
        │
        ▼
TEP process dynamics
        │
        ▼
XMEAS21 reactor cooling-water outlet temperature
```

A paired fault-versus-baseline experiment then showed substantial deviations in `XMV10` and `XMEAS21` during the fault window and persistent post-fault response. Across five independent seeds (42–46), the observed response was highly repeatable.

Representative five-seed ranges:

| Variable | Fault RMSE | Fault peak absolute deviation | Post RMSE |
|---|---:|---:|---:|
| XMEAS9 | 1.324–1.335 | 5.000 | 2.826–2.845 |
| XMV10 | 21.617–22.101 | 58.987–60.381 | 21.673–22.637 |
| XMEAS21 | 4.840–4.917 | 10.471–10.641 | 4.236–4.404 |

These results support the reproducibility of the **observed closed-loop response** across seeds. They are empirical benchmark evidence, not a formal causal proof.

## Fault-magnitude sweep

A three-magnitude × three-seed paired benchmark was also executed for sensor-bias magnitudes of `1`, `5`, and `10`.

Selected aggregate results:

| Magnitude | Variable | Fault RMSE mean | Fault IAE mean | Fault ISE mean | Post RMSE mean |
|---:|---|---:|---:|---:|---:|
| 1 | XMEAS9 | 0.324 | 0.119 | 0.052 | 0.400 |
| 1 | XMV10 | 9.320 | 3.420 | 43.435 | 11.478 |
| 1 | XMEAS21 | 1.837 | 0.701 | 1.687 | 2.131 |
| 5 | XMEAS9 | 1.328 | 0.491 | 0.878 | 2.837 |
| 5 | XMV10 | 21.873 | 9.600 | 239.139 | 22.120 |
| 5 | XMEAS21 | 4.881 | 2.037 | 11.910 | 4.315 |
| 10 | XMEAS9 | 3.335 | 1.290 | 5.546 | 12.073 |
| 10 | XMV10 | 28.946 | 12.854 | 418.897 | 41.059 |
| 10 | XMEAS21 | 7.149 | 2.798 | 25.552 | 0.607 |

The sweep demonstrates a reproducible magnitude-dependent response, but the response is not simply linear. In particular, `XMV10` error increases strongly while its maximum deviation appears bounded at the larger fault magnitudes. This behavior is now a specific research question rather than an assumption.

Issue #2 tracks the formal characterization of this response relationship, including scaling, nonlinearity/saturation, and post-fault recovery.

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
Scenario YAML / JSON             SCADA / HMI
        │                            │
        ▼                            │ OPC UA
   ScenarioRunner                    ▼
        │                      OPC UA FaultManagement
        └──────────────┐             │
                       ▼             ▼
                    FaultManager / lifecycle
                             │
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
           XMEAS/XMV     native IDV      provenance
           signal faults  process faults  + events
              │              │               │
              └──────────────┴───────────────┘
                             ▼
                        TEP process model
```

Signal-level faults operate at the TEP adapter boundary. Process disturbances are synchronized to the TEP model's native IDV interface. Both declarative and OPC UA paths preserve fault identity and temporal provenance.

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

The benchmark tooling now includes paired fault/baseline replication and fault-magnitude sweeps. Formal response characterization is tracked separately so that empirical results are not overstated.

### Evidence status

The current evidence establishes:

- reproducible experiment configuration
- persisted experiment and ground-truth metadata
- complete observation coverage for configured durations
- fault activation/deactivation at exact declared simulation boundaries
- OPC UA fault registration, listing, provenance, and lifecycle status transitions
- observed closed-loop response in expected controller/process variables
- repeatability across five random seeds for the controlled sensor-bias benchmark
- magnitude-dependent response across three fault magnitudes and three seeds

Still to be established:

- formal scaling/nonlinearity characterization
- response latency and settling-time characterization
- explanation of the apparent `XMV10` peak-deviation bound
- broader fault-family comparisons
- fault-attribution and detection metrics
- temporal-KG reasoning benchmarks
- comparisons against time-series-only and graph-enhanced AI baselines

These distinctions are intentional: **implemented**, **executed**, and **scientifically validated** are treated as different evidence levels.

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

Run the five-seed replication benchmark:

```powershell
python examples/run_replication.py `
  examples/experiments/reactor_cooling_bias_001.yaml `
  examples/scenarios/reactor_sensor_bias.yaml `
  examples/scenarios/reactor_no_fault.yaml `
  --seeds 42 43 44 45 46 `
  --output data/runs `
  --summary data/replications/reactor_cooling_bias.csv
```

Run the fault-magnitude sweep:

```powershell
python examples/run_fault_magnitude_sweep.py `
  examples/experiments/reactor_cooling_bias_001.yaml `
  examples/scenarios/reactor_sensor_bias.yaml `
  examples/scenarios/reactor_no_fault.yaml `
  --magnitudes 1 5 10 `
  --seeds 42 43 44 `
  --output data/runs
```

Start the OPC UA server:

```bash
python examples/run_opcua_server.py
```

The default endpoint is `opc.tcp://0.0.0.0:4841/process-sim/`. The launcher supports configurable endpoint, seed, real-time factor, and update interval options.

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

- ProfBraatz scientific reference
- backend-independent simulator boundary
- TEP adapter
- deterministic stepping and seeded runs
- measurements, manipulated variables, states, and disturbances
- engineering mappings and XMEAS units
- canonical observations/events

### Phase 2 — Industrial Twin Core — IN PROGRESS

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

### Phase 4 — OPC UA Integration — FAULT-MANAGEMENT FOUNDATION COMPLETE

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
- OPC UA fault injection and clearing methods
- operator fault provenance
- fault listing and lifecycle status (`registered` / `active` / `expired`)
- integration with the shared fault manager

Next:

- expose richer lifecycle notifications as first-class OPC UA Events
- semantic engineering names and units
- OPC UA EUInformation and quality/status/timestamps
- richer alarms and events
- external SCADA/HMI integration tests
- security and deployment configuration

### Phase 5 — Time-Series, Experiments, and Temporal Knowledge Infrastructure — EXPERIMENT FOUNDATION IMPLEMENTED

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
- paired fault/baseline replication tooling
- fault-magnitude sweep tooling
- initial benchmark matrix
- controlled closed-loop response experiments

Next:

- formal fault-response characterization
- automated benchmark aggregation and statistical analysis
- historian/time-series backend integration
- temporal event model expansion
- event-to-observation correlation
- temporal knowledge graph schema and replay/query interfaces

### Phase 6 — Engineering & Semantic Digital Thread — PROTOTYPE IMPLEMENTED; INTEGRATION IN PROGRESS

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

### Phase 8 — Web SCADA / HMI — FRONTEND PROTOTYPE; LIVE INTEGRATION PLANNED

- browser-based operational interface
- live process visualization
- trends and historical views
- alarms and events
- scenario controls
- operator actions
- engineering-name and semantic metadata integration

The intended operational path is **SCADA/HMI → OPC UA → control/process layer**, not direct access to simulator internals.

### Phase 9 — Knowledge Graph & GraphRAG — VISUALIZATION PROTOTYPE; RDF/GRAPHRAG PLANNED

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

The immediate research task is **formal characterization of the fault-magnitude response relationship**. This should be completed before expanding the platform into semantic reasoning or GraphRAG benchmarks.

The intended evaluation questions are:

1. Does temporal knowledge improve operational-context retrieval compared with time-series-only retrieval?
2. Do engineering relationships plus telemetry improve fault and root-cause identification?
3. Does explicit provenance reduce unsupported or unverifiable AI conclusions?
4. Can the same semantic identity connect engineering, enterprise, simulation, and operational representations consistently?

The TEP should remain a controlled, reproducible experimental environment while the platform grows toward a provenance-aware industrial digital thread.