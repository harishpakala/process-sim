# process-sim

**Industrial process simulation and digital-twin research platform**  
Harish Kumar Pakala

`process-sim` uses the Tennessee Eastman Process (TEP) to explore process simulation, engineering information integration, operational history, and evidence-grounded retrieval.

**TEP NEXUS** is the repository's simulation-based semantic–temporal retrieval prototype. It connects AAS-derived engineering information in GraphDB with simulation-run-specific observations in TimescaleDB through explicit engineering-to-signal mappings and an on-demand Virtual Temporal Knowledge Graph (VTKG).

## Architecture

| Component | Purpose |
| --- | --- |
| TEP simulator and OPC UA | Process simulation and operational signals |
| GraphDB | Engineering RDF and cross-domain relationships |
| TimescaleDB | Run-specific measurements and recorded events |
| TEP NEXUS | Mapping resolution, constrained retrieval, VTKG construction, and evidence validation |
| Vue Web UI | Simulation controls and engineering / historian queries |

The prototype uses predefined read-only retrieval operations and application-controlled validation. Engineering-to-signal mappings and product associations are provisional; the system is not a production-certified digital twin.

## Quick start

**Windows PowerShell**, from the repository root:

```powershell
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Start the optional TimescaleDB historian:

```powershell
docker compose -f docker-compose.timeseries.yml up -d
```

Start each service in a separate terminal:

```powershell
# OPC UA simulation server
$env:PYTHONPATH="$PWD\src"
python examples/run_opcua_server.py --endpoint "opc.tcp://0.0.0.0:4841/process-sim/" --seed 42 --real-time-factor 1.0
```

```powershell
# HTTP API
$env:PYTHONPATH="$PWD\src"
python -m process_sim.api.server
```

```powershell
# Web UI
cd frontend
npm run dev
```

Open the URL printed by Vite and start the simulation using the Web UI. **GraphDB and published engineering RDF are required for TEP NEXUS semantic retrieval**; follow the [semantic setup guide](semantic/README.md) to create repository `AAST` and publish the graphs. Historian persistence and temporal queries additionally require TimescaleDB.

## Engineering Models

The Tennessee Eastman reactor engineering diagrams are available in [`docs/engineering-models/`](docs/engineering-models/).

### Reactor P&ID

[Open the reactor P&ID diagram](docs/engineering-models/tep-reactor-pid.png)

![TEP reactor piping and instrumentation diagram](docs/engineering-models/tep-reactor-pid.png)

### Reactor ECAD

[Open the reactor ECAD diagram](docs/engineering-models/tep-reactor-ecad.png)

![TEP reactor electrical CAD diagram](docs/engineering-models/tep-reactor-ecad.png)

## Documentation

- [Experimental Docker Compose development stack](docs/docker-stack.md)
- [Historian and TimescaleDB setup](docs/opcua/TIMESERIES.md)
- [Semantic lifting and GraphDB setup](semantic/README.md)
- [TEP NEXUS evaluation and reproducibility](docs/artifact_evaluation/README.md)
- [SELiRA research prototype](selira_integration/README.md)
- [Detailed project notes](docs/project-history-and-research-notes.md)

## Research

TEP NEXUS builds on **ONTO:NEXUS**: [*From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems*](https://doi.org/10.1145/3837062.3839557).

The experimental results describe a bounded simulation-based implementation; a fresh clone does not include the exact historical run evidence needed to reproduce every reported result.
