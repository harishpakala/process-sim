## SELiRA implementation and evaluation status (experimental)

This branch introduces a **standalone, offline-testable correspondence qualification foundation** in `src/process_sim/selira/`. It does not replace existing `/api/semantic/asset-history` behavior, change the TEP simulator, or claim that GraphDB operational references are independently validated.

| Capability | Status | Evidence |
| --- | --- | --- |
| Legacy operational-reference recognition | Existing implementation | `src/process_sim/api/asset_history.py`; `mapped` means one recognized signal, **not** semantic validation |
| Candidate-level qualification and response-level resolution | Implemented on this branch | `selira/contracts.py`, `selira/resolution.py` |
| Explicit reviewed declaration and nonempty evidence reference requirement | Implemented as **structural checks only** | `selira/resolution.py`; evidence authenticity is **not** independently verified |
| Fail-closed authoritative-use policy | Implemented as reusable function, **not wired into production endpoints** | `selira/consumer_policy.py` |
| Applicability evaluation against engineering configuration | Planned | The branch accepts declared `applicable`/`inapplicable`/`unknown` status; it does not calculate it |
| GraphDB integration, independent evidence verification, service endpoints | Planned | No new deployed endpoint on this branch |
| Reproducible end-to-end and quantitative evaluation | Not yet performed | Offline unit tests added, execution/CI status must be checked separately |

**Offline tests** (with project installed in editable mode or `PYTHONPATH=src`):

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_selira_resolution.py' -v
```

**Semantics:** An extracted `XMEAS`/`XMV` identifier is a candidate, not a validated correspondence. A unique candidate without a reviewed declaration remains unresolved. A validated declaration requires an evidence reference and declared applicability, but these fields are **assertions**, not independent proof. Conflicting declarations fail closed; competing unresolved signals produce ambiguity. The consumer-policy function permits authoritative use only for an unambiguously selected, validated, applicable candidate with evidence references.

**Next implementation increments:** connect the resolver to authoritative AAS/GraphDB evidence and validation profiles; evaluate applicability against configurations; expose contract-bearing service responses; integrate consumer checks; add injected-error and false-withholding evaluations. Preserve the legacy asset-history response contract during migration.

# process-sim

**Author:** Harish Kumar Pakala

`process-sim` is an open industrial process simulation and digital-twin platform. It starts with the Tennessee Eastman Process (TEP) as the scientific reference model and is designed to evolve into an industrial knowledge, temporal-data, and AI platform.

The project deliberately separates the **reference process model** from the surrounding platform. The ProfBraatz TEP implementation remains the scientific baseline; `process-sim` provides the Python boundary, orchestration, industrial integration, recording, fault/scenario infrastructure, semantic modeling, and future AI foundations around it.

## Local startup — API, OPC UA, web UI, TimescaleDB, GraphDB and Ollama (Windows PowerShell)

This is a **multi-terminal development setup**, not a single all-in-one server. Run the commands from the repository root unless a step changes directory. Use the same checkout for the API, OPC UA server, frontend and scripts. Python must be able to import `process_sim` from `src`; Node.js/npm, Docker (for the sample database), GraphDB and Ollama are separate prerequisites. The local HTTP API is unauthenticated and bound to loopback by default; do not expose it to untrusted networks.

### 1. Install dependencies (once per Python environment)

```powershell
cd C:\Users\haris\Documents\GitHub\process-sim
python -m pip install -r requirements-opcua.txt -r requirements-timeseries.txt
cd frontend
npm install
cd ..
```

If your checkout is instead under `C:\Users\haris\Documents\GitHub\ps_olama\process-sim`, use that location consistently. Install any additional project requirements required by your selected TEP backend; the commands above specifically cover the OPC UA and historian integration.

### 2. Start TimescaleDB (optional, required for persistent history)

**Terminal A** — with Docker Desktop running:

```powershell
docker compose -f docker-compose.timeseries.yml up -d
docker compose -f docker-compose.timeseries.yml ps
```

The supplied Compose configuration uses PostgreSQL/TimescaleDB on `127.0.0.1:5432`, database `tep_nexus`, user `tep`, and a **local-development-only** password `tep-local-dev`. Configure a different `TEP_DB_PASSWORD` before first startup for other environments. If you already use an existing TimescaleDB installation, **do not start a second database or overwrite its credentials**: use that installation's actual DSN instead. The API creates/updates its schema on startup when `TEP_TIMESCALE_DSN` is set.

### 3. Start the OPC UA simulation server

**Terminal B**:

```powershell
$env:PYTHONPATH="$PWD\src"
python examples/run_opcua_server.py --endpoint "opc.tcp://0.0.0.0:4841/process-sim/" --seed 42 --real-time-factor 1.0
```

This is the **TEP simulator's OPC UA server**, not the Python HTTP API. The server exposes `TEP/Simulation` (including `Start`, `Stop`, `Reset`), `XMEAS1..41`, `XMV1..12` and fault-management methods. It starts in **manual/external OPC UA control mode**: XMV commands must come from an external controller; starting the server alone does not establish closed-loop control. For local clients, use `opc.tcp://127.0.0.1:4841/process-sim/` if the endpoint is reachable. Keep this terminal running.

### 4. Start GraphDB (for semantic queries and asset resolution)

Start your **existing GraphDB installation** and confirm that repository `AAS` exists and contains the imported AssetInventory and ProductCatalog RDF graphs. Workbench is normally at `http://localhost:7200`; the SPARQL endpoint is `http://localhost:7200/repositories/AAS`. GraphDB is not started by the TimescaleDB Docker Compose file. If the graphs have not yet been loaded, consult [semantic/README.md](semantic/README.md) for lifting/import and validation. The asset-history endpoint needs the `assetinventory:hasOperationalReference` triples.

### 5. Start the Python HTTP API and historian

**Terminal C** — start after the OPC UA server; configure environment variables in **this terminal** before launching:

```powershell
$env:PYTHONPATH="$PWD\src"
$env:TEP_TIMESCALE_DSN="postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus"
$env:GRAPHDB_SPARQL_ENDPOINT="http://localhost:7200/repositories/AAS"
python -m process_sim.api.server
```

**Replace the example DSN with your existing database connection string if applicable.** Without `TEP_TIMESCALE_DSN`, the API can still provide a short in-memory history, but persistent run/signal/fault history and automatic GraphDB run synchronization are unavailable. With a configured DSN, the API starts an OPC UA polling historian and a GraphDB synchronization worker by default. The historian collects all 41 XMEAS and 12 XMV signals as simulation time advances. The worker publishes **run/signal/fault provenance metadata**, not all high-frequency samples, to separate GraphDB named graphs. Set `$env:TEP_GRAPH_SYNC="0"` before startup to disable automatic GraphDB writes. Consult [docs/opcua/TIMESERIES.md](docs/opcua/TIMESERIES.md) for details and limitations.

Verify in another PowerShell window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/health"
Invoke-RestMethod "http://127.0.0.1:8000/api/simulation/status"
Invoke-RestMethod "http://127.0.0.1:8000/api/simulation/history"
Invoke-RestMethod "http://127.0.0.1:8000/api/semantic/sync/status"
Invoke-RestMethod "http://127.0.0.1:8000/api/simulation/runs"
```

The HTTP API defaults to `http://127.0.0.1:8000` (`PROCESS_SIM_API_HOST` and `PROCESS_SIM_API_PORT` override the bind address and port). `/api/health` checks the API process only; use `/api/simulation/status` to test OPC UA connectivity, `/api/simulation/history` to inspect historian persistence/storage errors, and `/api/semantic/sync/status` to inspect GraphDB synchronization. A running API is **not** proof that the simulator is advancing; start it through its OPC UA `Start()` method or an integrated control UI/client.

### 6. Start the Vue web interface

**Terminal D**:

```powershell
cd frontend
npm run dev
```

Open the **Local** URL printed by Vite (typically `http://localhost:5173`). Vite proxies `/api` requests to `http://127.0.0.1:8000` by default; override with `PROCESS_SIM_API_URL` when needed. Some engineering/product graph views are local AAS-JSON previews, **not** live GraphDB visualizations. Do not assume every frontend view is wired to the running OPC UA service.

### 7. Ollama — separate local grounded Q&A

Start Ollama separately and install the model expected by the GraphDB Q&A script:

```powershell
ollama pull llama3.1:8b
ollama list
Invoke-RestMethod "http://127.0.0.1:11434/api/tags"
```

If the Ollama service is not already running, start it using your local Ollama installation (for example, `ollama serve` in a separate terminal). **Ollama is not automatically started by the Python API or Vue frontend**, and the existing Q&A scripts are command-line tools, not HTTP API routes.

The **repository-tracked** GraphDB/ProductCatalog question-answering prototype:

```powershell
python scripts/ask_graphdb_ollama.py "TEP_XMEAS7 pressure transmitter" --evidence-only
python scripts/ask_graphdb_ollama.py "Which product is associated with TEP_XMEAS7?"
python scripts/ask_graphdb_ollama.py "Explain the engineering significance and verification limitations of the product association for TEP_XMEAS7."
python scripts/ask_graphdb_ollama.py "Which product is associated with TEP_NONEXISTENT_999?"
```

The outputs distinguish `EVIDENCE_ONLY`, `DETERMINISTIC_GROUNDED_RESPONSE`, `GROUNDED_RESPONSE`, and `NO_EVIDENCE`. A deterministic answer is **not** an Ollama generation; a no-evidence response is retrieval-layer abstention. Product associations and ECLASS mappings may be provisional and must not be represented as verified physical installation. See [docs/local-ollama-graphdb-grounding.md](docs/local-ollama-graphdb-grounding.md).

**Locally tested historical Q&A script (not yet tracked on `main`):** if you have separately saved `scripts/ask_historical_ollama.py` in this checkout, you can run:

```powershell
python scripts/ask_historical_ollama.py TEP_XMEAS6 --run-id 5636ccad-cc2a-41ae-9032-3d2f52bd0185 --evidence-only
python scripts/ask_historical_ollama.py TEP_XMEAS6 --run-id 5636ccad-cc2a-41ae-9032-3d2f52bd0185
```

This requires the API, GraphDB, TimescaleDB historical run, and Ollama. The run ID above is **an example from a validated local dataset**, not guaranteed to exist in a fresh database. It resolves an AssetInventory asset to an operational signal and retrieves historical values via `GET /api/semantic/asset-history` before prompting Ollama. It is **not** yet part of the server/frontend and does not implement general causal diagnosis.

### Shutdown and troubleshooting

Use `Ctrl+C` in the OPC UA, API, Vite and optional Ollama terminal windows. To stop only the sample TimescaleDB container while preserving its volume, run `docker compose -f docker-compose.timeseries.yml down` (do **not** add `-v` unless you intend to delete stored data).

- **OPC UA unavailable:** confirm port 4841 is free, the OPC UA process is running, and `/api/simulation/status` reports connectivity.
- **No persistent samples:** check `TEP_TIMESCALE_DSN`, `/api/simulation/history` → `storageError`, whether the simulator is advancing, and the correct database/run ID.
- **GraphDB sync errors:** verify repository `AAS`, the SPARQL endpoint, GraphDB write permissions, and `/api/semantic/sync/status`.
- **Ollama errors:** verify `/api/tags` and `ollama list`; the Q&A CLI needs a locally available model.
- **Frontend API errors:** keep the API on port 8000 or configure `PROCESS_SIM_API_URL` for Vite.

## Deferred milestone — Physical BOM revision governance

**Status: Deferred by project decision (23 October 2026).** Do not treat this as completed or production-ready.

The initial Engineering Relationship Registry, server-side append-only review history, evidence-gated physical membership review, and immutable physical BOM revision overlays have been implemented as a prototype. The next governance milestone is intentionally postponed:

- **Complete physical BOM revision supersession:** explicitly designate a new current baseline and supersede previous revisions without rewriting historical snapshots.
- **Revision comparison:** display additions, removals, and changed equipment-parent assignments between any two physical BOM revisions.
- **Withdrawal and correction:** record withdrawal/rejection of previously approved physical assignments through new audit events, preserving prior decisions and preventing stale evidence from authorizing new releases.
- **Formal release workflow:** validate a proposed complete physical BOM baseline, require review and evidence for every change, and record release metadata and approval history.
- **Production readiness:** verify end-to-end tests and frontend build; assess durable backups, document evidence/version integrity, access controls if deployed beyond a trusted local environment, and stronger independent audit integrity.

**Engineering constraints:** Functional correspondence is not physical installation; neither establishes DEXPI–ECAD identity. Source EBOM `ParentItemId` must remain unchanged until explicitly justified by verified physical evidence and an approved revision process. Existing immutable revision overlays are not automatically superseded when later evidence is withdrawn.

Implementation details: [Engineering review workflow](docs/engineering-review-workflow.md).

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

### ProductCatalog — selected commercial products (engineering decision, October 2026)

The following **seven existing commercial product entries** are present in the TEP NEXUS ProductCatalog. ECLASS class names and IRDIs were supplied during engineering review; the classifications are documented here **before** changes to the AAS JSON, ECAD references, or AssetInventory. These are representative commercial products, not hardware specified by the original Tennessee Eastman benchmark.

| Manufacturer | Selected product / function | ECLASS class | Preferred name | ECLASS class IRDI | Qualification |
|---|---|---|---|---|---|
| SMC | **PFMV505-1** — minute-flow sensor | 27-27-48 | Flow sensor | `0173-1#01-AHB183#005` | Selected; verify process medium and measurement range for any installed location |
| IFM | **LW2720** — non-contact 80 GHz radar level sensor | 27-20-05-05 | Free-space radar level transmitter/switch | `0173-1#01-AAC024#022` | Selected; radar-specific class supersedes the provisional generic level-transmitter class |
| Schneider Electric | **A9MEM3555** — three-phase electricity meter | 27-14-23-16 | Electronic electricity meter | `0173-1#01-AFZ828#022` | Selected; measures an AC electrical circuit, not the modeled 24 V DC instrument bus |
| SAMSON | **Type 3241-7** — pneumatic globe control valve, DN25, Kvs 10 m³/h, PN40 | 37-01-02-03 | Control globe valve | `0173-1#01-AAD651#023` | Selected representative assembly: Type 3277 actuator, Type 3730-1 4–20 mA positioner, normally closed; requires instrument air |
| SMC | **PSE550** — low differential-pressure sensor | 27-20-06-23 | Pressure differential sensor | `0173-1#01-AKA491#001` | Selected; low differential-pressure gas measurement, not automatically suitable for high-pressure TEP streams |
| Phoenix Contact | **2938581** / QUINT-PS-100-240AC/24DC/5 — industrial power supply | 27-04-07-04 | AC-DC supply | `0173-1#01-AFX043#011` | Selected; 24 V DC, 5 A nominal output; check total connected load |
| IFM | **TA1101** — integrated temperature sensor/transmitter | 27-27-51 | Temperature sensor | `0173-1#01-AHB186#005` | Selected instead of the previously considered passive Pt100 TM4101; verify exact signal-interface details against its datasheet |

**SAMSON part-number provenance:** Tetra Pak's Plant Components catalog lists **`90533-1149`** for the **3241-7 / 3730-1, DN25, Kvs 10.00 m³/h** assembly. This is a **Tetra Pak supplier/catalog part number**, **not a verified SAMSON manufacturer order number**. Keep supplier and manufacturer identifiers separate in the future ProductCatalog AAS. The supplied listing also specifies DIN PN40 flanges, cast-steel GS-C25 housing, Type 3277 pneumatic actuator, Type 3730-1 positioner (4–20 mA), normally closed operation, and an included air-reducing station. Its heading says “SS/SS,” while the detailed housing field says GS-C25; do not silently infer a stainless-steel housing.

**Explicit exclusions and replacements:**

- **SMC PSH-L2-01-W** humidity/condensation checker — removed from the intended ProductCatalog scope.
- **Rittal 3244100** enclosure filter fan — removed from the intended ProductCatalog scope; existing ECAD motor-device references to this fan part number require correction, not reuse as a motor.
- **Siemens S55264-V193** HVAC pressure-independent valve — superseded by the selected **SAMSON Type 3241-7** representative process-control valve.
- **IFM TM4101** passive Pt100 temperature sensor — considered but superseded by **IFM TA1101**.
- The earlier generic **LW2720** candidate `27-20-05-18` / `0173-1#01-AAC030#023` is superseded by the radar-specific `27-20-05-05` class. Float-switch classification `27-27-31-05` is inapplicable.

**Implementation status:** This section records **agreed selections only**. The source `examples/aas/product_catalog_instance.json` still reflects the prior eight-product snapshot until a separate implementation commit; the seven-product selection has **not** yet been written into that AAS instance. The earlier counts and cross-domain part-number match statistics in this README refer to the existing snapshot and must be recalculated after changes. Validate manufacturer/supplier identity, electrical/pneumatic connections, DEXPI/ECAD/AssetInventory references, ECLASS release compatibility, and SHACL/RDF lifting after implementation.

### Classification rules and evidence boundaries

- **ProductCatalog AAS** should hold the authoritative ECLASS classification for a product type; **AssetInventory AAS** should reference that product for each installed asset. Validate actual inventory coverage before claiming every physical asset is classified.
- Each `0173-1#01-...#...` identifier above is an **ECLASS class IRDI**. Do not reuse it as the semantic ID of an unrelated AAS property such as `DeviceType`.
- Classify the **driven machine** and its **electric motor** separately only where the motor is represented as a distinct asset. The agitator's *complete* assembly classification must not be confused with the standalone motor classification.
- The recycle compressor's broad 36-43 class avoids an unsupported assumption about rotary positive displacement, reciprocating compression, or turbo compression. **Confirm whether the parent class is directly assignable** in the selected ECLASS release before implementing the ProductCatalog mapping.
- The gas–liquid separator selection assumes a **vessel separator**. The TEP process model does not specify separator internals.
- The eleven globe-valve selections and the synchronous-motor selection are **TEP NEXUS modeling assumptions** rather than verified original TEP equipment specifications. XMV(12) denotes agitator speed control, **not a twelfth physical control valve**.
- Synchronous motors require appropriate electrical drive arrangements. A 24 V DC instrumentation supply does **not** by itself establish suitable motor power or drive compatibility. ECAD power distribution and motor-drive details remain a separate consistency review.
- ProductCatalog AAS entries include ECLASS class and IRDI values; the working equipment classifications still require ECLASS release/assignability verification. AssetInventory classification coverage must be checked separately.

### Reviewed alternatives not selected

- **Linear DC motor** (`0173-1#01-ADJ119#015`) and **Linear induction motor** (`0173-1#01-ADJ117#015`): linear rather than rotary motion.
- **Universal motor** (`0173-1#01-AKE157#019`): rotary, but not the selected continuous industrial-drive technology.
- **Electric motor (motor vehicle)** (`0173-1#01-AFX525#006`) and **Motor (hydraulics, other)** (`0173-1#01-AGU935#004`): incorrect application domain or energy-conversion technology.
- **Submersible motor pump** (`0173-1#01-AKL848#022`): assumes submerged pump construction and describes a pump unit rather than a standalone drive motor.
- **Compressor (positive type, rotating)** (`0173-1#01-AAD586#013`), **Compressor (special execution)** (`0173-1#01-AAD589#012`), and **Compressor, ventilator, vacuum pump (other)** (`0173-1#01-AKL925#012`): not selected without evidence of the specified design or an actual *other* subtype.

**Next implementation step:** validate the updated ProductCatalog JSON against the AAS template and SHACL shapes, verify ECLASS class assignability, then reconcile product/asset references before any RDF publication or AssetInventory linking. Keep ECAD electrical topology changes separate from this documentation step.

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

## Research evaluation strategy — evidence-grounded industrial AI

**Status (25 October 2026): evaluation protocol proposed; systematic benchmark results are not yet available.** This plan supports the research direction *Towards Evidence-Grounded AI in Industrial Automation: A Semantic Reference Architecture*. The architecture is intended to be reusable across industrial automation systems; **TEP NEXUS is the initial reference implementation**, not evidence of general portability. The evaluation follows a two-level principle inspired by the component-level and end-to-end evaluation design of *Req2Road* (CAiSE 2026, [arXiv:2602.15591](https://arxiv.org/abs/2602.15591)); its experiments and outcomes are not claimed to be equivalent.

### Evaluation questions

- **RQ1 — Semantic identity:** Can AssetInventory assets be resolved to the correct, unambiguous operational signals and historical observations?
- **RQ2 — Evidence traceability:** Can each supported engineering statement be traced to the right asset, simulation run, observations, timestamps, and data source?
- **RQ3 — Claim reliability:** Do independent numerical/temporal checks and evidence-bounded responses reduce unsupported statements and improve appropriate abstention compared with less-constrained baselines?
- **RQ4 — Portability (future):** Which architectural contracts can be reused in a second automation environment without TEP-specific assumptions?

### Component-level experiments

| ID | Experiment | Procedure and ground truth | Primary measures |
|---|---|---|---|
| **E1** | Semantic asset-to-signal resolution | Audit the 41 XMEAS and 12 XMV signal identities against explicit AssetInventory operational references; manually adjudicate ambiguous or missing links. Do not assume full mapping coverage. | Mapping coverage, precision/recall on adjudicated cases, false-link and ambiguity-detection rates |
| **E2** | Run-specific evidence retrieval and provenance | Query multiple recorded runs; compare returned observations, run IDs, ordering, values, and timestamps against independent historian queries and recorded manifests. Include nonexistent runs and missing data. | Evidence retrieval accuracy, run/time consistency, attribution accuracy, missing-evidence handling |
| **E3** | Numerical and temporal claim verification | Construct correct and deliberately corrupted statements about latest values, deltas, direction, timestamps, and run identity; test independent checks. | Detection precision/recall, false rejection rate, unsupported numerical/temporal claim rate |
| **E4** | Evidence-grounded AI reliability | Evaluate the same question set across controlled baseline configurations, including answerable and unanswerable questions. Independently adjudicate semantic and causal assertions. | Answer correctness, claim faithfulness, appropriate abstention, false causal attribution, latency |

**Fault-aware cases** may use seeded TEP disturbances and fault events to test retrieval of recorded fault context. An injected fault label does **not** by itself prove that a specific measurement change has a unique cause. Full root-cause analysis remains planned and must not be reported as an evaluated capability.

### Baselines and ablations

Use the same model version, question set, generation settings, and comparable evidence windows where applicable. Record exactly what each configuration receives:

| Configuration | Input and mechanisms | Purpose |
|---|---|---|
| **B1 — Ungrounded LLM** | Question and general scenario description; no retrieved operational measurements | Measure unsupported answering without access to evidence; **not** a fair numerical-information baseline |
| **B2 — Historical-evidence LLM** | Question plus historian observations with signal, run, and time context | Test whether supplying operational evidence is sufficient |
| **B3 — Semantic-grounded LLM** | B2 plus explicit AAS/GraphDB asset resolution and provenance | Isolate the benefit of semantic binding and source attribution |
| **B4 — Semantic grounding + verification** | B3 plus independent claim checks, rejection/repair policy, and evidence-bounded abstention | Test verification benefits and costs |

For a controlled **verification ablation**, compare B3 and B4 on *identical retrieved evidence*. For a **semantic-resolution ablation**, evaluate cases where identity is genuinely ambiguous or mismatched; do not attribute gains to semantics when the baselines already receive the correct identity. Record deterministic responses separately from model-generated responses: a rule-based answer is **not** an LLM answer that passed verification.

### End-to-end feasibility

Demonstrate a reproducible engineering question through:

```text
Engineering question
    -> AssetInventory identity / GraphDB operational reference
    -> Run-specific TimescaleDB observations
    -> Evidence package (source, identity, run, time, values)
    -> Numerical / temporal verification
    -> Evidence-bounded answer or explicit abstention
```

Capture the exact query, asset IRI, signal, run ID, source observations, expected result, produced answer, verification status, and latency. Report any stages not exercised live; an existing historical query path does not automatically establish continuous OPC UA-to-historian-to-graph synchronization. No MES or standalone ERP integration is currently demonstrated.

### Benchmark design and reproducibility

- **Initial target, not a result:** audit up to 53 operational signals; collect 5–10 reproducible runs and approximately 30–50 manually reviewed engineering scenarios as a feasibility benchmark. Expand to 150–250 questions and repeated LLM trials if resources permit.
- Include factual retrieval, trend/delta, run-specific, missing-evidence, ambiguous-mapping, unsupported-causality, and (if implemented) fault-context questions.
- Create ground-truth records independently of model output using historian queries, graph assertions, controlled simulation manifests, and human review for ambiguous or causal cases.
- Pin code commit, graph snapshot, database snapshot/run IDs, model identifier/version, prompts, seeds where supported, temperature, hardware, and timeouts. Preserve per-question inputs, outputs, decisions, and timings.
- Report per-category denominators, failure examples, uncertainty intervals where justified, and threats to validity. Do not generalize from a single process, model, or corrected answer to all industrial systems.

### Current evidence and limits

- A previously recorded TEP run contains **145,856 signal samples**, covering **53 signals** and **2,752 timestamps**; selected asset-history values were compared with the historian.
- In one XMEAS6 historical question, an Ollama response incorrectly characterized a decrease as unchanged. A subsequent **deterministic** response correctly computed the delta and declined unsupported causal attribution. This demonstrates a specific failure and mitigation, **not** a measured overall reliability improvement.
- A valid asset with a nonexistent run produced a `NO_EVIDENCE` result. More negative cases and an automated regression suite are required.
- The current historical Q&A CLI uses TEP-specific signal validation; reuse outside TEP is a design objective, not yet an evaluated property.
- Numerical token screening is not full semantic verification. The present causal-question path bypasses the LLM and should be analyzed as a distinct deterministic response policy.

**Minimum publishable evaluation package:** E1–E4 with independently established ground truth, B2/B3/B4 comparisons, at least one complete traceable workflow, negative cases, reproducible artifacts, and an explicit limitations discussion. The evaluation plan does not predetermine positive results.

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
