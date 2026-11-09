# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin research platform. It uses the Tennessee Eastman Process (TEP) as its scientific reference model and provides a foundation for investigating industrial process simulation, engineering information integration, operational data retrieval, and AI-assisted engineering applications.

The project deliberately separates the **reference process model** from the surrounding platform. The TEP implementation provides the process model, while `process-sim` provides simulation orchestration, industrial interfaces, measurement recording, event management, semantic integration, and research evaluation capabilities.

## TEP NEXUS — Semantic–Temporal Digital Twin Architecture

TEP NEXUS is a research implementation within `process-sim` that investigates engineering-context-preserving retrieval across heterogeneous engineering information and simulation-specific operational data.

Its architecture combines:

- **GraphDB:** AAS-derived engineering information and semantic relationships.
- **TimescaleDB:** Simulation-specific measurements and recorded events.
- **Engineering-to-signal mappings:** Explicit associations between engineering functions and operational signals.
- **Virtual Temporal Knowledge Graph (VTKG):** On-demand integration of engineering context and run-scoped observations.
- **Application layer:** Constrained retrieval, evidence validation, and deterministic response reconstruction.

The implementation is evaluated using a simulation-based Tennessee Eastman Process configuration.



## Research Paper — DTwiSE 2027

**Target venue:** International Workshop on Digital Twin Software Engineering (DTwiSE 2027), co-located with ICSE 2027.

The associated research investigates how digital-twin software can preserve engineering context when retrieving execution-specific operational measurements and recorded events.

The paper evaluates:

- Cross-domain engineering reference resolution.
- Engineering-to-operational-signal mapping.
- Simulation-run-aware temporal retrieval.
- On-demand Virtual Temporal Knowledge Graph construction.
- Constrained LLM-mediated retrieval and evidence validation.
- Deterministic response reconstruction and rejection behavior.

**Research artifact:** [Artifact Evaluation and Reproducibility Guide](docs/artifact_evaluation/README.md).

The exact experiment files and outputs corresponding to the manuscript are being consolidated into a versioned research artifact. The reported results should be interpreted within the stated simulation configuration and evaluation limitations.

Recorded operator injection commands are distinguished from independently verified fault activation.

---

## 1. Project Objectives

The project investigates software engineering approaches for connecting process simulation, engineering information, and operational data within an industrial digital-twin environment.

The main objectives are:

1. Provide a controlled process simulation environment for digital-twin experimentation.
2. Integrate engineering information from heterogeneous engineering representations.
3. Connect engineering functions with operational signals through explicit references and mappings.
4. Retrieve measurements and events under simulation-run and temporal constraints.
5. Investigate semantic integration and evidence-grounded AI interaction.
6. Support reproducible evaluation of digital-twin software architectures.

## 2. Architecture Overview

The platform separates process simulation, operational data management, semantic engineering information, and application services.

### 2.1 Process Simulation Layer

The Tennessee Eastman Process provides a controlled chemical-process simulation environment.

The simulation environment supplies process measurements, manipulated variables, operating conditions, and recorded simulation events.

The selected TEP implementation and its signal conventions are documented separately from the conventional benchmark specification.

### 2.2 Operational Data Layer

TimescaleDB stores simulation-specific operational measurements and recorded events.

Measurements retain their simulation-run context and temporal information. Simulation time is distinguished from recording timestamps to support execution-aware retrieval.

### 2.3 Semantic Engineering Layer

GraphDB stores RDF representations of engineering information derived from Asset Administration Shell (AAS) Submodel Templates and Instances.

The engineering representations include:

- DEXPI process-engineering information.
- ECAD electrical-engineering information.
- AssetInventory.
- ProductCatalog.
- Engineering Bill of Materials (EBOM).
- OPC UA Connectivity.

Explicit references associate corresponding engineering entities across these representations.

Engineering-to-signal mappings connect selected engineering functions with operational signal identifiers.

The completeness and physical validity of these relationships depend on the underlying engineering data and mapping evidence.

### 2.4 Semantic–Temporal Integration

TEP NEXUS introduces an on-demand Virtual Temporal Knowledge Graph (VTKG).

The VTKG combines engineering relationships retrieved from GraphDB with selected observations retrieved from TimescaleDB.

It provides a request-scoped representation connecting:

- Engineering functions.
- Assets and engineering entities.
- Operational signals.
- Simulation runs.
- Retrieved observations.
- Source references and provenance information.

The VTKG avoids permanently materializing the complete historian as RDF.

### 2.5 Application and Retrieval Layer

The application layer coordinates engineering resolution, operational retrieval, and evidence processing.

An optional locally deployed language model proposes structured retrieval plans and evidence-grounded responses.

Application logic validates permitted operations and retrieval constraints before executing predefined, read-only database operations.

Generated answers undergo deterministic evidence checks. When answer validation fails, the application can reconstruct responses directly from retrieved evidence.

Retrieval failures are reported rather than repaired through language generation.

---

## 3. Implemented Research Capabilities

The following capabilities are investigated within the current TEP NEXUS implementation.

| Capability | Description |
|---|---|
| AAS semantic representation | Ontology-oriented engineering information and RDF representations |
| Engineering traceability | Explicit cross-domain engineering references |
| Signal resolution | Engineering-function-to-operational-signal mappings |
| Temporal retrieval | Run-specific and simulation-time-constrained observations |
| Virtual graph construction | On-demand integration of engineering and operational evidence |
| Query constraints | Structured requests and predefined read-only operations |
| Evidence validation | Deterministic checks on retrieved identifiers and observations |
| Response reconstruction | Evidence-only fallback when generated answers fail validation |
| Evaluation | Pipeline benchmarks, SQL comparisons, negative tests, and engineering questions |

The implementation is a research prototype, not a continuously synchronized physical digital twin.

---

## 4. Repository Structure

The repository contains simulation software, semantic integration components, application services, and research evaluation artifacts.

| Directory | Purpose |
|---|---|
| `simulation/` | Process simulation and orchestration components |
| `semantic/` | Semantic representations and engineering information integration |
| `docs/` | Architecture, implementation, and research documentation |
| `tests/` | Software and integration tests |
| `scripts/` | Execution, validation, and evaluation utilities |
| `experiments/` | Experimental configurations and evaluation artifacts |

The exact directory structure may evolve as the implementation develops.

For component-specific instructions, consult the documentation within the corresponding directory.

## Local startup (Windows PowerShell)

Run these commands from the repository root. Start each long-running service in a separate terminal.

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
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
python -m pip install -r requirements.txt
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

**SC-01 — Semantic Information Contract: Asset-to-Product Reference Consistency.** Validates that each applicable `AssetInventory` asset's product reference resolves to exactly one authoritative `ProductCatalog` entry at the evaluated source revision (`|P_ν(a)| = 1`). Outcomes: **V** (one verified match), **F** (zero or multiple matches with complete evidence), **U** (incomplete, missing, or stale evidence), and **NA** (asset outside the contract scope). Relevant source changes require reassessment. This identifier-consistency check does **not** establish product suitability or consumer authorization.

### Proposed additional SELiRA contracts (not yet verified end-to-end)

The following compact definitions are **proposed** evaluation obligations. They do not imply that authoritative evidence, live integration, or production enforcement is implemented. All use **V** (validated), **F** (invalid), **U** (insufficient, incomplete, or stale evidence), and **NA** (demonstrably outside scope). Relevant source, configuration, or policy changes require reassessment.

| ID | Type | Contract | Compact definition |
| --- | --- | --- | --- |
| **SC-02** | Engineering Validation Contract | Engineering-to-Signal Meaning Consistency | Validates that a mapped operational signal measures the intended engineering property on the correct equipment, with compatible physical meaning and units under the applicable configuration. **V:** all checks evidenced; **F:** authoritative contradiction; **U:** evidence insufficient; **NA:** mapping outside scope. |
| **SC-03** | Engineering Validation Contract | Configuration and Revision Applicability | Validates that a correspondence and its supporting engineering evidence apply to the requested configuration and source revisions. **V:** applicability and currency evidenced; **F:** proven mismatch; **U:** applicability or revision unknown; **NA:** outside scope. |
| **CAC-01** | Consumer Acceptance Contract | Operational Evidence Fitness | Accepts an otherwise validated engineering-to-signal correspondence for operational analysis only when the requested run/time interval, units, provenance, and measurement coverage satisfy the consumer's task requirements. **V:** requirements met; **F:** known requirement violated; **U:** evidence incomplete; **NA:** task outside scope. |
| **CAC-02** | Consumer Acceptance Contract | Engineering Restriction Fitness | Accepts an otherwise validated engineering restriction for a SAFSL-style specification task only when its approval, target property, units, and configuration satisfy the consumer's requirements. **V:** requirements met; **F:** known mismatch; **U:** approval or context unknown; **NA:** task outside scope. |

**Boundary:** SC-02 and SC-03 concern source-side engineering validity. CAC-01 and CAC-02 concern task-specific fitness for use and cannot override failed, pending, or ambiguous source qualification. These identifiers and definitions are documentation proposals, not claims about the existing SC-02–SC-06 implementation specifications.

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

## SELiRA contracts (proposed formal representations)

The following table summarizes the proposed SELiRA contract types and their responsibilities. **SC-01** is a Semantic Information Contract; **SC-02 and SC-03** are proposed Engineering Validation Contracts; **CAC-01 and CAC-02** are proposed Consumer Acceptance Contracts. These definitions do not imply complete implementation or end-to-end enforcement.

| ID | Type | Contract | Purpose |
| --- | --- | --- | --- |
| SC-01 | Semantic Information | Asset-to-Product Reference Consistency | Ensures a unique product reference. |
| SC-02 | Engineering Validation | Engineering-to-Signal Meaning Consistency | Checks property meaning, equipment identity, units, and configuration. |
| SC-03 | Engineering Validation | Configuration and Revision Applicability | Checks whether engineering evidence applies to the requested configuration and revision. |
| CAC-01 | Consumer Acceptance | Operational Evidence Fitness | Checks whether measurements satisfy an operational analysis task. |
| CAC-02 | Consumer Acceptance | Engineering Restriction Fitness | Checks whether an engineering restriction is suitable for a SAFSL-style specification task. |

**Scope note:** SC-02 and SC-03 are proposed names in this overview and are not asserted to replace the existing SC-02–SC-06 specifications without reconciliation. CAC acceptance requires qualified engineering evidence and does not override failed or unresolved validation.

## TEP NEXUS simulation information contracts (separate reference)


The following **TEP-specific simulation information contracts** describe information exposed or recorded by the reference simulator. They are compact architectural representations, **not** Engineering Validation Contracts (SCs) or Consumer Acceptance Contracts (CACs). Their generic, TEP-independent counterparts remain to be derived. Tuple fields and constraints are not necessarily implemented or independently verified by `TEPAdapter`.

| ID | Type | Contract | Mathematical representation | Purpose |
| --- | --- | --- | --- | --- |
| TEP-C01 | Simulation information | [Simulation](docs/architecture/contracts/tep-c01-simulation.md) | `C_sim(k) = (B, S_k, T_k, Δt, R, Q)` | Describes simulation state, time, backend, seed, and control mode. |
| TEP-C02 | Simulation information | [Measurements](docs/architecture/contracts/tep-c02-measurements.md) | `C_meas(i,k) = (I_i, V_(i,k), U_i, T_k, R_run, P)` | Describes 41 XMEAS signals and their observation context. |
| TEP-C03 | Simulation information | [Manipulated variables](docs/architecture/contracts/tep-c03-manipulated-variables.md) | `C_ctrl(i,k) = (I_i, V_(i,k), T_k, Q, P)` | Describes 12 XMV signals and their control context. |
| TEP-C04 | Simulation information | [Native disturbances](docs/architecture/contracts/tep-c04-disturbances.md) | `C_dist(i,k) = (I_i, A_(i,k), T_s, D, P)` | Describes 20 native IDV slots and disturbance scheduling. |
| TEP-C05 | Simulation information | [Faults and scenarios](docs/architecture/contracts/tep-c05-fault-scenarios.md) | `C_fault(f) = (I_f, F_f, X_f, M_f, T_s, D, P)` | Describes fault identity, target, scheduling, and provenance. |

Each linked specification defines its tuple elements, a core constraint, and information origins. **Run identity and provenance come from recording/event infrastructure**, not necessarily the native simulator.

**Relation to SELiRA:** These contracts describe available simulation information. **SC-01 (Semantic Information Contract)** checks a separate asset-to-product reference relationship. **Engineering Validation Contracts (SCs)** evaluate whether claimed engineering correspondences are supported by applicable authoritative evidence. **Consumer Acceptance Contracts (CACs)** determine whether qualified information meets a specific consumer task's requirements. For example, `XMEAS7` identifies a TEP measurement channel but does not, by itself, establish the physical engineering asset it measures or authorize its use in a consumer workflow.

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
