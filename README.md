# process-sim

**Industrial process simulation and digital-twin research platform** · Author: Harish Kumar Pakala

`process-sim` uses a Tennessee Eastman Process (TEP) simulation to study process behavior, engineering information integration, operational history, and evidence-grounded information retrieval. The process model and the surrounding software platform are distinct: the platform provides orchestration, OPC UA interfaces, recording, semantic integration, and evaluation tools.

**TEP NEXUS** is the semantic–temporal retrieval research implementation within this repository. It is a **simulation-based prototype**, not a continuously synchronized physical plant digital twin or a production-certified engineering system.

## Start here

| I want to… | Go to |
| --- | --- |
| Run the local platform and Web UI | [Local startup](#local-startup-windows-powershell) |
| Understand the TEP NEXUS architecture | [Architecture at a glance](#architecture-at-a-glance) |
| Configure historian persistence | [TimescaleDB / OPC UA guide](docs/opcua/TIMESERIES.md) |
| Review the research experiment | [Artifact evaluation guide](docs/artifact_evaluation/README.md) |
| Explore SELiRA semantic correspondence and validation research | [SELiRA research documentation](docs/research/selira/selira-contract-alignment.md) · [Integration prototype](selira_integration/README.md) |
| Consult detailed project history, contracts, and roadmap | [Archived detailed README](docs/project-history-and-research-notes.md) |

## Engineering diagrams and AAS JSON models

The repository includes illustrative reactor engineering diagrams and the AAS source files used for semantic integration. Instrument and product associations are provisional, not independently verified physical installations.

- **Engineering diagrams:** [Reactor P&ID](docs/engineering-models/tep-reactor-pid.png) · [Reactor ECAD](docs/engineering-models/tep-reactor-ecad.png)
- **DEXPI:** [Template](examples/aas/dexpi_template.json) · [Instance](examples/aas/tep_dexpi_instance.json)
- **ECAD:** [Template](examples/aas/ecad_template.json) · [Instance](examples/aas/tep_ecad_instance.json)
- **AssetInventory:** [Template](examples/aas/asset_inventory_template.json) · [Instance](examples/aas/asset_inventory_instance.json)
- **ProductCatalog:** [Template](examples/aas/product_catalog_template.json) · [Instance](examples/aas/product_catalog_instance.json)
- **Engineering BOM:** [Template](examples/aas/engineering_bom_template.json) · [Instance](examples/aas/tep_engineering_bom_instance.json)
- **OPC UA Connectivity:** [Template](examples/aas/opcua_connectivity_template.json) · [Instance](examples/aas/tep_opcua_connectivity_instance.json)

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

Start GraphDB with repository `AAS`, then generate and publish the engineering RDF from the repository root:

```powershell
python -m semantic.template_lifting --push
python -m semantic.instance_lifting --validate --push
```

These commands use the configured default domains (DEXPI, ECAD and ProductCatalog). `--validate` runs local SHACL validation for instance lifting, while `--push` uploads generated RDF to GraphDB. Check the validation output and GraphDB configuration before relying on the published data. See [semantic setup](semantic/README.md) for details.

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

The frontend is built with **Vue 3, TypeScript, and Vite**. Its development commands are included above, so no separate frontend setup guide is needed. Some schematic connections are illustrative rather than verified DEXPI piping; the process simulation runs in the backend, not in the browser.

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

## Research evaluation

The **TEP NEXUS 36-query benchmark** evaluates engineering-function queries, limited-scope answer validation, and execution latency. See the [artifact-evaluation guide](docs/artifact_evaluation/README.md) for all 36 questions, recorded results, and reproduction instructions. Reproducing the historical run requires its run-specific evidence and configuration; a fresh clone alone is insufficient.

For the semantic-lifting research foundation, see ONTO:NEXUS: [*From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems*](https://doi.org/10.1145/3837062.3839557).
