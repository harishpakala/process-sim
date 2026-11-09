# process-sim

**Industrial process simulation and digital-twin research platform** · Author: Harish Kumar Pakala

`process-sim` uses a Tennessee Eastman Process (TEP) simulation to study process behavior, engineering information integration, operational history, and evidence-grounded information retrieval. The process model and the surrounding software platform are distinct: the platform provides orchestration, OPC UA interfaces, recording, semantic integration, and evaluation tools.

**TEP NEXUS** is the semantic–temporal retrieval research implementation within this repository. It is a **simulation-based prototype**, not a continuously synchronized physical plant digital twin or a production-certified engineering system.

## Start here

| I want to… | Go to |
| --- | --- |
| Run the local platform and Web UI | [Local startup](#local-startup-windows-powershell) |
| Understand the TEP NEXUS architecture | [Architecture at a glance](#architecture-at-a-glance) |
| Work with AAS, RDF, SHACL, or GraphDB | [Semantic setup](semantic/README.md) |
| Configure historian persistence | [TimescaleDB / OPC UA guide](docs/opcua/TIMESERIES.md) |
| Review the research experiment | [Artifact evaluation guide](docs/artifact_evaluation/README.md) |
| Explore SELiRA semantic correspondence and validation research | [SELiRA research documentation](docs/research/selira/selira-contract-alignment.md) · [Integration prototype](selira_integration/README.md) |
| Browse frontend-specific instructions | [Frontend README](frontend/README.md) |
| Consult detailed project history, contracts, and roadmap | [Archived detailed README](docs/project-history-and-research-notes.md) |

## Architecture at a glance

| Component | Responsibility |
| --- | --- |
| TEP simulation and OPC UA | Controlled simulation, measurements, and operator commands |
| TimescaleDB | Run-specific signal samples and recorded events |
| AAS engineering representations | DEXPI, ECAD, AssetInventory, ProductCatalog, EBOM, and OPC UA Connectivity |
| GraphDB | RDF engineering entities, references, and cross-domain relationships |
| Engineering-to-signal mappings | Explicit links between engineering functions and operational signals |
| Virtual Temporal Knowledge Graph (VTKG) | On-demand, request-scoped integration of selected engineering relationships and historian observations |
| Application / optional local LLM | Constrained retrieval, evidence validation, and evidence-only response reconstruction |
| Vue Web UI | Simulation, engineering, and AI-query interfaces |

**Retrieval boundary:** The local language model may propose structured requests, but application logic validates constraints and executes predefined read-only operations. It cannot submit executable SQL or SPARQL. A rejected generated answer may be reconstructed from retrieved evidence; failed retrieval is not repaired through language generation.

**Evidence boundary:** Logical mappings and product candidates do not prove installed hardware, verified physical units, or sensor identity. A recorded injection command does not independently establish fault activation or causality. The VTKG has not been benchmarked against direct application-level database composition.

## Local startup (Windows PowerShell)

Run commands from the repository root. Keep long-running services in separate terminals. Python, Node.js/npm, and Docker (if using the sample TimescaleDB service) must be installed.

**1. Install Python and frontend dependencies**

```powershell
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

**2. Start TimescaleDB** (optional for the basic simulator; required for persistent historian and temporal questions)

```powershell
docker compose -f docker-compose.timeseries.yml up -d
```

See [historian configuration](docs/opcua/TIMESERIES.md). Use your own DSN if you already have a database.

**3. Start the OPC UA simulation server** (terminal A)

```powershell
$env:PYTHONPATH="$PWD\src"
python examples/run_opcua_server.py --endpoint "opc.tcp://0.0.0.0:4841/process-sim/" --seed 42 --real-time-factor 1.0
```

This command starts the **OPC UA service**, not the simulation run. Once the service and API are available, use the **Web UI** to start, stop, or reset the TEP simulation. Starting the service does not establish closed-loop control or create the historical run used in the paper.

**4. Prepare GraphDB** (required for GraphDB-backed semantic queries)

Start GraphDB with repository `AAS` and load the required engineering RDF. Follow [semantic setup](semantic/README.md); starting an empty repository is insufficient.

**5. Start the HTTP API and historian** (terminal B)

```powershell
$env:PYTHONPATH="$PWD\src"
$env:TEP_TIMESCALE_DSN="postgresql://tep:tep-local-dev@127.0.0.1:5432/tep_nexus"
$env:GRAPHDB_SPARQL_ENDPOINT="http://localhost:7200/repositories/AAS"
python -m process_sim.api.server
```

The DSN above is a **local-development example**, not a production credential. Omit or replace it if persistent history is not required. Check `http://127.0.0.1:8000/api/health`. Historian samples require an advancing simulation.

**6. Start the Vue Web UI** (terminal C)

```powershell
cd frontend
npm run dev
```

Open the URL printed by Vite (typically `http://localhost:5173`). **Operate the simulation from the browser** using the simulation controls, then use the **Fault Management** view to inject, inspect, or clear faults. Some engineering views use local AAS JSON rather than live GraphDB.

### Operate the simulation and faults from the Web UI

![TEP simulation controls in the Web UI](docs/images/simulation-control.png)

*Simulation Control: use the browser controls to start, stop, or reset the TEP simulation.*

After starting the OPC UA server, HTTP API, and Vue frontend, use this interactive workflow:

1. **Simulation control:** Start the TEP simulation from the Web UI. Check the reported running state and advancing simulation time. Use **Stop** to stop execution and **Reset** when a fresh simulation state is needed.
2. **Fault Management:** Choose a fault type (`process_disturbance`, `bias`, `drift`, or `stuck`), select a target, configure the magnitude or value and duration, then select **Inject fault**. The frontend sends the request through `/api/simulation/faults` to the OPC UA fault-management methods.
3. **Inspect and clear:** The Fault Management view lists registered faults and offers **Clear** and **Clear all**. Fault statuses returned by the service should be read as recorded simulator state, not as independent evidence of physical effects.
4. **Monitor and analyze:** Use the Web UI's measurements, historian, and TEP NEXUS query views as applicable. Persistent run-specific history requires the configured TimescaleDB historian and an advancing simulation.

#### Example: Inject Fault-01 — XMEAS9 bias

Start the simulation in the Web UI and confirm that simulation time is advancing. Open **Fault Management** and enter these exact settings:

| Web UI field | Value |
| --- | --- |
| **Fault ID** | `Fault-01` |
| **Fault type** | **Bias** (`bias`) |
| **Target** | **XMEAS9** (reactor temperature; sometimes written `XMEAS09`) |
| **Magnitude** | **5** |
| **Duration (simulation hours)** | **0** |
| **Stuck value** | Not applicable for a bias fault |

![Fault Management form configured for Fault-01, Bias, XMEAS9, magnitude 5, duration 0](docs/images/fault-01-configuration.png)

*Fault-01 configuration in the Web UI. Verify the form values before selecting Inject fault.*

Select **Inject fault**. The Web UI submits the injection request to the simulation API and OPC UA fault-management interface. Refresh or inspect **Registered faults** to find `Fault-01` and its reported status. The displayed status and a successful API response are simulator records; they do not independently establish that the expected measurement change occurred.

**Duration `0` means indefinite**, not zero-length: the fault remains registered for ongoing application until explicitly cleared (or the simulation state is reset). To remove it, select **Clear** next to `Fault-01` and confirm. The magnitude is entered in the simulator's bias parameter; do not infer independently calibrated physical units or a verified +5 °C effect solely from the request.


**Important distinction:** Starting the platform's OPC UA/API services is an infrastructure step; **Start/Stop/Reset and fault injection are interactive Web UI operations**. Simulation lifecycle and fault injection are operated through the Web UI. A successful injection request records an operator command; it does not, by itself, independently verify fault activation.

**7. Optional: run local Ollama**

```powershell
ollama pull llama3.1:8b
python scripts/ask_graphdb_ollama.py "Which product is associated with TEP_XMEAS7?"
```

Ollama must be running. This is a standalone GraphDB-grounded CLI, not the complete live TEP NEXUS validation pipeline. See [Ollama grounding](docs/local-ollama-graphdb-grounding.md).

**Shutdown:** Stop foreground processes with `Ctrl+C`. To stop the sample database without deleting its data: `docker compose -f docker-compose.timeseries.yml down`. Check ports 4841 (OPC UA), 8000 (API), 7200 (GraphDB), and 11434 (Ollama) when troubleshooting.

## Research evaluation and reproducibility

The TEP NEXUS research investigates engineering reference resolution, signal mapping, run-scoped temporal retrieval, virtual graph construction, constrained AI interaction, and deterministic evidence checks.

The [artifact evaluation and reproducibility guide](docs/artifact_evaluation/README.md) describes the selected evidence, evaluation procedures, limitations, and required inputs. **The exact reported experiment is not yet reproducible from a fresh clone alone**: run-specific inputs and outputs still need an immutable, versioned artifact bundle. Do not substitute historical question sets or runs.

The Web UI paper-question workflow and the separately executed evidence-conditioned Ollama assessment are **not equivalent experiments**. The 12-question qualitative assessment does not establish live VTKG accuracy or independent verification of engineering mappings.

## Implementation scope and documentation

- **Implemented research foundations:** simulation orchestration, OPC UA interfaces, recording, AAS-derived engineering representations, and selected semantic–temporal retrieval paths. Deployment and verification depend on configured services and populated data.
- **Experimental or incomplete:** SELiRA correspondence qualification and consumer authorization, live integration of some engineering views, production hardening, model-evolution handling, and broader performance comparisons.
- **Not claimed:** standalone ERP or MES implementation, independently verified installed instruments, fully autonomous industrial AI, or a physically synchronized plant digital twin.

The original long-form README, including dated milestone tables, equipment candidates, proposed contracts, and historical research decisions, is preserved **without modification** in [Project history and research notes](docs/project-history-and-research-notes.md). Its dated status reports are historical snapshots, not a substitute for checking current code and tests.

For the semantic-lifting research foundation, see ONTO:NEXUS: [*From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems*](https://doi.org/10.1145/3837062.3839557).
