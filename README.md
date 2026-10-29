# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Local startup (Windows PowerShell)

Run these commands from the repository root. Start each long-running service in a separate terminal.

### 1. Install dependencies

```powershell
python -m pip install -r requirements-opcua.txt -r requirements-timeseries.txt
cd frontend
npm install
cd ..
```

### 2. Start TimescaleDB (optional)

```powershell
docker compose -f docker-compose.timeseries.yml up -d
```

Required for persistent historian data; omit if using an existing database. See [time-series setup](docs/opcua/TIMESERIES.md).

### 3. Start the OPC UA simulation server

```powershell
$env:PYTHONPATH="$PWD\src"
python examples/run_opcua_server.py --endpoint "opc.tcp://0.0.0.0:4841/process-sim/" --seed 42 --real-time-factor 1.0
```

The simulator starts in external-control mode; starting it does not automatically establish closed-loop control.

### 4. Start GraphDB (optional for semantic features)

Start your existing GraphDB service with repository `AAS` and the required RDF graphs. See [semantic setup](semantic/README.md).

### 5. Start the HTTP API and historian

```powershell
$env:PYTHONPATH="$PWD\src"
$env:TEP_TIMESCALE_DSN="postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus"
$env:GRAPHDB_SPARQL_ENDPOINT="http://localhost:7200/repositories/AAS"
python -m process_sim.api.server
```

Adjust the example DSN to your database; omit it when persistent history is unnecessary. The sample credentials are for local development only. Check `http://127.0.0.1:8000/api/health`. The historian requires an advancing simulation.

### 6. Start the Vue web interface

```powershell
cd frontend
npm run dev
```

Open the local URL printed by Vite (typically `http://localhost:5173`). Some engineering views use local AAS JSON rather than live GraphDB.

### 7. Ollama (optional, standalone Q&A)

```powershell
ollama pull llama3.1:8b
python scripts/ask_graphdb_ollama.py "Which product is associated with TEP_XMEAS7?"
```

Ollama must be running separately. This script is a GraphDB-grounded CLI, **not** an integrated SELiRA verifier. See [Ollama grounding](docs/local-ollama-graphdb-grounding.md).

### Shutdown and troubleshooting

Stop foreground services with `Ctrl+C`. Stop the sample database with `docker compose -f docker-compose.timeseries.yml down` (without `-v` to retain data). For connection issues, check ports 4841 (OPC UA), 8000 (API), 7200 (GraphDB), and 11434 (Ollama), plus the configured database DSN. See [time-series troubleshooting](docs/opcua/TIMESERIES.md).

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

## SELiRA — Experimental implementation status

SELiRA provides an offline-testable correspondence qualification foundation in `src/process_sim/selira/`. An extracted XMEAS/XMV identifier is a **candidate**, not independently validated engineering correspondence.

| Component | Current status |
| --- | --- |
| Candidate qualification and correspondence resolution | Implemented; handles rejected, conflicting, and ambiguous candidates |
| Fail-closed consumer authorization | Reusable policy implemented; **not wired into production endpoints** |
| GraphDB candidate retrieval | Experimental adapter; offline mocked tests reported passing |
| Guarded historian access | Experimental function; **not integrated into the existing production API or web UI** |
| Engineering evidence validation | Prototype for selected TEP pressure tags; project-scope checks are not authenticated physical evidence |
| GraphDB named-graph evidence inspection | Experimental; mocked tests reported passing, live query unverified |
| Synthetic policy comparison | 18 deterministic declaration-driven scenarios; **not** an empirical real-world accuracy benchmark |
| End-to-end operational validation | Not demonstrated |

**Tests:** The latest reported local run passed **42/42 SELiRA tests**; another **10 semantic regression tests** passed in separate runs. These are user-reported local results, not independently verified CI or live integration results.

**Limitations:** Independent evidence authenticity, configuration applicability, live GraphDB/TimescaleDB integration, and production API enforcement remain incomplete or unverified. Existing `/api/semantic/asset-history` behavior is unchanged.

## Operational and enterprise integration clarification (24 October 2026)

The merged code contains an OPC UA polling historian, optional TimescaleDB persistence for simulation runs, signal samples and fault commands, a temporal RDF exporter, and a GraphDB synchronization worker. These are **implemented in source**, not independently verified as a live end-to-end deployment. High-frequency samples remain in TimescaleDB; GraphDB receives run/signal/fault provenance metadata. Asset-to-signal operational references are not proof of physical installation.

**ERP scope:** There is **no standalone ERP implementation**. The AssetInventory AAS is the current enterprise-relevant asset-information representation; it must not be described as an operational ERP system or a verified ERP integration. **MES scope:** no MES functionality is implemented. MES and standalone ERP integrations are future work, not completed architecture layers. These distinctions also apply to CAiSE 2027 claims.

## Current development milestone — Semantic Digital Thread prototype (October 2026)

The active integration milestone is **Phase 6 — Engineering & Semantic Digital Thread**, with early user-interface work from Phases 8 and 9. This is a prototype milestone, **not** completion of the full semantic digital thread or the GraphRAG phase.

| Phase | Roadmap status | Implemented in the current milestone | Still required |
|---|---|---|---|
| 1 — TEP reference integration | Foundation complete | TEP adapter, deterministic simulation boundary, engineering measurements | Ongoing maintenance |
| 2 — Industrial twin core | In progress | Simulation lifecycle and run context | Canonical cross-domain plant/asset model, operating-state semantics |
| 3 — Faults and scenarios | Foundation implemented | Fault manager, scenarios, lifecycle events and native disturbances | Extended fault families, schema validation and comparisons |
| 4 — OPC UA | Fault-management foundation complete | Simulation controls, XMEAS/XMV and fault-management methods | OPC UA events, security, engineering metadata and external HMI verification |
| 5 — Temporal data and experiments | Historian and experiment foundations implemented in source; runtime verification pending | Parquet recording, controlled experiments, OPC UA polling historian, optional TimescaleDB run/signal/fault persistence, temporal RDF export and GraphDB sync worker | Reproducible live historian/GraphDB trace, failure/recovery tests, expanded benchmarks |
| **6 — Engineering & Semantic Digital Thread** | **Prototype implemented; integration/validation in progress** | AAS templates and example instances for DEXPI, ECAD and ProductCatalog; configurable RDF template/instance lifting scripts; ProductCatalog engineering audit and provisional equipment candidates | RDF-level completeness audit and repeatable CI validation; GraphDB ingestion; cross-domain identity and provenance; QUDT/eCl@ss enrichment |
| 7 — BOM and enterprise | AssetInventory AAS and engineering BOM prototype present; standalone ERP and MES not implemented | AssetInventory AAS represents enterprise-relevant asset information; ProductCatalog and engineering BOM/review prototypes provide related engineering data | Standalone ERP, MES, enterprise transactions, approved physical BOM governance and cross-system identity resolution |
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
- The DEXPI source includes **5 equipment**, **22 instrumentation functions**, and **12 actuating functions**. the historical source check counted **8 ProductCatalog products**; the current ProductCatalog JSON has **14 entries (7 existing products + 7 provisional candidates)**, and AssetInventory contains **62 assets** in that historical check.

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

## Provisional TEP equipment candidates — engineering decision (October 2026)

**Status: CONCEPTUAL / SUBJECT TO CHANGE — NOT ENGINEERING APPROVED, PROCURED, OR INSTALLED.**

The TEP benchmark does not specify actual commercial equipment. We have paused further 24-hour control-dynamics and steady-state experiments for now, while continuing the semantic digital-twin prototype with **seven provisional manufacturer-backed equipment-family candidates**. The observed slow pressure/stripper-loop oscillations do **not** establish that steady state is impossible. Appropriate PID/cascade retuning, nonlinear control, model-predictive control, or other control changes may improve the behavior, but **none of these improvements has yet been demonstrated**. Control changes may change the operating envelope and therefore trigger new equipment sizing and compatibility assessments. Control improvements cannot make a vessel rated below the actual operating pressure mechanically suitable.

The [equipment manufacturer selection register](docs/equipment_manufacturer_selection_register.md) records the source evidence, operating-fit gaps, and revalidation triggers. The AAS source [`examples/aas/product_catalog_instance.json`](examples/aas/product_catalog_instance.json) now includes **seven existing commercial product entries plus seven provisional engineered-equipment candidates (14 total)**. The seven provisional candidates are:

| Equipment function | Provisional manufacturer offering | Status / critical qualification |
|---|---|---|
| Reactor | De Dietrich customized high-pressure reactor inquiry | **Requires alternative to standard BE**: published +6 bar standard BE pressure rating does not cover the observed ~27 bar(g) service; no certified custom unit selected |
| Condenser | Alfa Laval Olmi engineered shell-and-tube | Provisional; duty, materials and design pressure unverified |
| Gas–liquid separator | Didion Vessel Type DSL | Provisional; mechanical rating and phase-loading performance unverified |
| Recycle compressor | Atlas Copco GT-Series centrifugal | Provisional; compressor map, gas compatibility and drive sizing unverified |
| Stripper | Sulzer engineered stripping column/unit | Provisional; specific pressure-rated configuration for ~31 bar(g) service unverified |
| Reactor agitator | EKATO HWL-N | Provisional; speed, torque, seals and selected configuration unverified |
| Separate drive motors | ABB AMZ synchronous family | Provisional comparison only; motor technology and individual drive ratings unverified |

These candidate AAS collections use `SelectionStatus`, `EvidenceSource`, `OperatingEnvelopeBasis`, `FitGaps` and `RevalidationTriggers`. Their `AssetIdentifier` values are **research candidate identifiers**, not installed asset IDs. The ECLASS class/IRDI assignments are **working mappings pending verification** against the selected ECLASS release. No candidate is linked as a selected or installed product in AssetInventory. Adding these JSON records does **not** imply that RDF lifting, SHACL validation, GraphDB publication or the frontend have been rerun or verified after this change.

**Revalidate candidates** after controller changes, revised simulation/fault envelopes, process design-basis updates, manufacturer datasheets, ECLASS checks or engineering sign-off. Do not promote provisional candidates to approved products without configuration-specific evidence.

## ProductCatalog and AssetInventory AAS

The two AAS submodels separate **product-type definitions** from **engineering asset instances**. The following tables summarize fields found in the current JSON instances; they are not catalogs of verified physical installations.

### ProductCatalog AAS

| Information | Implemented AAS field(s) | Purpose |
| --- | --- | --- |
| Product identity | `AssetIdentifier` | Identifies the product-type definition. |
| Manufacturer and designation | `ManufacturerName`, `ManufacturerPartNumber`; `ManufacturerProductDesignation` where present | Identifies the supplier's product/model. |
| ECLASS classification | `ECLASSClass`, `ECLASSPreferredName`, `ECLASSIRDI` | Describes the assigned product class and identifier. |
| Technical specifications | `TechnicalProperties` | Records product-specific technical characteristics. |
| Engineering and verification status | `SelectionStatus`, `ECLASSVerificationStatus` and other status fields where present | Distinguishes proposed selections from independently verified claims. |

### AssetInventory AAS

| Information | Implemented AAS field(s) | Purpose |
| --- | --- | --- |
| Asset identity | `AssetId`, `AssetName`, `EquipmentTag` | Identifies the engineering asset or equipment tag. |
| Asset type and location | `AssetType`, `Location` | Describes the asset's engineering context. |
| Product association | `ProductReference`; `CandidateProductReference` where present | Connects an asset to a product definition or a provisional candidate. |
| Operational signal | `OperationalReference` where present | Records a signal reference; its presence alone does **not** establish validated semantic correspondence. |
| Engineering reference | `EngineeringReference` where present | Points to related engineering information. |
| Modeling and integration status | `ModelingStatus`, `SimulationStatus`, `MonitoringStatus` | Records declared status; not an independent SELiRA certification. |

**Source artifacts:** [ProductCatalog JSON](examples/aas/product_catalog_instance.json) and [AssetInventory JSON](examples/aas/asset_inventory_instance.json). Not every asset has a product reference or engineering reference, and provisional assignments must not be treated as verified installations. Historical equipment/ECLASS selection decisions remain in [the engineering decision register](docs/engineering/eclass-classification-decisions.md) for reconciliation.

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

## Research foundation

The semantic-modeling strategy is grounded in the author's ONTO:NEXUS workshop paper, part of MODELS 2026:

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

## TEP NEXUS contracts (proposed specification)

TEP NEXUS distinguishes **TEP-specific contracts** (the observable behavior of the Tennessee Eastman reference implementation) from **generic platform contracts** (reusable interfaces that must not assume TEP signal names or simulator internals). The TEP-specific contracts will be specified and checked against the existing implementation **before** their generic counterparts are derived. The entries below are a **specification plan**, not a claim that all guarantees are implemented or formally verified.

| ID | TEP-specific contract | Scope to specify |
| --- | --- | --- |
| **TEP-C01** | Simulation lifecycle and time | Initialization, reset, stepping, states, simulation clock, seed and determinism boundaries |
| **TEP-C02** | Measurements (XMEAS) | 41 measurement identities, values, units, sampling, time and run context |
| **TEP-C03** | Manipulated variables (XMV) | 12 control-variable identities, read/write semantics, constraints and failure behavior |
| **TEP-C04** | Native disturbances (IDV) | 20 disturbance slots, activation, duration and synchronization with native simulation steps |
| **TEP-C05** | Fault and scenario execution | Signal faults, scheduled lifecycle, declarative scenarios, events and provenance |

**Formal contract template:** Each contract will define typed operations and data; preconditions; postconditions; invariants; temporal/state-transition rules; explicit failure semantics; provenance; and verification evidence. Every requirement must be marked **implemented and tested**, **implemented but unverified**, or **specified but not implemented**. Timing and determinism guarantees must be established from actual simulator and adapter behavior, not assumed.

**Architectural boundary:** A TEP signal such as `XMEAS7` is an operational signal identifier, **not proof of engineering asset identity**. Mapping it to an AAS asset requires separate semantic correspondence and evidence qualification. Generic contracts and SELiRA evidence/authorization contracts will be defined after the TEP-specific behavior is established.

## Fault and scenario engineering

TEP NEXUS supports declarative fault scenarios, including sensor bias, drift, actuator faults, and native TEP process disturbances. Fault execution is integrated with simulation orchestration and recording, preserving fault identity and temporal provenance. Signal-level faults operate at the TEP adapter boundary, while process disturbances use the model's native IDV interface.

## Research evaluation

The proposed evidence-grounded AI evaluation protocol, baselines, and evidence limitations are documented in [Research evaluation strategy](docs/research/evaluation-strategy.md). Systematic benchmark results are not yet available.

## Roadmap — Remaining Work

This table tracks outstanding work rather than repeating capabilities already documented as implemented. **Prototype**, **foundation implemented**, and **integrated/validated** are distinct maturity levels.

| Area | Current maturity | Remaining work |
| --- | --- | --- |
| Industrial Twin Core (Phase 2) | In progress | Complete richer equipment and functional relationships, lifecycle/run management, operating-state transitions, and source-generated events. |
| Fault Injection & Scenarios (Phase 3) | Foundation implemented | Add schema validation, richer scheduling, noise/saturation/intermittent/combined faults, controller and communication faults, reusable scenario libraries, and experiment comparisons. |
| OPC UA Integration (Phase 4) | Fault-management foundation implemented | Expose first-class lifecycle events, engineering names and units, EUInformation, quality/status/timestamps, richer alarms, external SCADA/HMI integration tests, and deployment security. |
| Time-Series & Experiments (Phase 5) | Experiment foundation implemented | Characterize fault responses, automate benchmark aggregation and statistics, integrate historian/time-series backends, expand temporal event models, and support event-to-observation correlation and replay/query. |
| Engineering & Semantic Digital Thread (Phase 6) | Prototype implemented; integration in progress | Complete cross-domain identity/provenance reconciliation, template governance, ECLASS/AAS verification, SHACL validation, and end-to-end semantic integration and evaluation. |
| BOM & Enterprise Integration (Phase 7) | Planned | Model EBOM/MBOM/service BOM, master data, ERP references, manufacturer/supplier identifiers, revisions, lifecycle status, and enterprise-to-engineering identity resolution. |
| Web SCADA / HMI (Phase 8) | Frontend prototype; live integration planned | Integrate live OPC UA data, trends/history, alarms, scenario controls, operator actions, and engineering/semantic metadata. Intended path: **SCADA/HMI → OPC UA → control/process layer**. |
| Knowledge Graph & GraphRAG (Phase 9) | Visualization prototype; RDF/GraphRAG integration planned | Integrate and validate engineering/temporal graphs, SPARQL competency queries, graph-grounded retrieval, and provenance-aware answers; distinguish experimental adapters from production integrations. |
| Industrial AI Platform (Phase 10) | Planned | Develop evidence-backed diagnosis, root-cause and temporal reasoning, engineering-aware recommendations, controlled agent actions, and benchmarked comparisons. |

**Completed foundation:** Phase 1 (TEP reference and Python simulation integration) is omitted from the remaining-work table. Implementation status elsewhere in this README describes existing foundations; items above should not be interpreted as delivered or independently validated.
### Deferred: Physical BOM revision governance

The Engineering Relationship Registry and immutable physical BOM revision overlays exist as prototypes. **Full supersession, revision comparison, correction/withdrawal audit, formal release approval, and production hardening remain deferred**, not completed. Physical installation must not be inferred from functional correspondence. See [Engineering review workflow](docs/engineering-review-workflow.md).

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
