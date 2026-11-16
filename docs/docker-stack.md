# Local Docker Compose stack (experimental)

This is an **initial, unverified development deployment** of the existing process-sim services. It does not change SELiRA or replace the documented non-Docker setup.

## Prerequisites

- Docker Engine / Docker Desktop with Compose v2
- Sufficient memory for GraphDB, TimescaleDB, Node, and the Python services
- Access to the GraphDB image specified by `GRAPHDB_IMAGE`; verify its availability, version, and license for your use case before distributing or publishing images

## Start

From the repository root:

```sh
docker compose up -d --build
docker compose ps
```

Open the Vue UI at http://localhost:5173 and GraphDB Workbench at http://localhost:7200. The Python API is at http://localhost:8000. Database port 5432 and OPC UA port 4841 are exposed to the host loopback only.

Containers communicate through Docker DNS names (`api`, `graphdb`, `timescaledb`, `simulator`). The Vite development server proxies `/api` to `http://api:8000`. Data persists in named `graphdb_data` and `tep_timeseries` volumes.

**Required first-time GraphDB setup:** GraphDB does not automatically contain repository `AAST`. Create it in GraphDB Workbench, then publish the engineering RDF from the existing `semantic/ontology2/` Turtle files as appropriate for your evaluation. Until repository creation and graph import are complete, engineering and historian-semantic queries may fail. A repeatable initialization service is a planned follow-up.

**Historian setup:** TimescaleDB starts with database `tep_nexus`, but this Compose file does not yet validate historian schema migration or an end-to-end simulation recording. Confirm initialization and persistence before reporting benchmark results.

**GraphDB image:** The default is `ontotext/graphdb:10.8.0` as a starting configuration, not a verified distributable image. Override it with `GRAPHDB_IMAGE` if your licensed/available distribution uses another reference.

**Local development only:** The password fallback `tep-local-dev` is not secure for production. Put a private `TEP_DB_PASSWORD` in an ignored `.env` file. No TLS or application authentication is configured. Do not expose the stack publicly.

## Stop

```sh
docker compose down
```

Volumes are preserved. **Do not run** `docker compose down -v` unless you intentionally want to erase local database volumes.

## Verification checklist (not yet executed)

1. `docker compose config` validates.
2. Images build and all five services start.
3. GraphDB `AAST` exists and contains the intended engineering graphs.
4. UI `/api` calls reach the Python backend.
5. OPC UA simulator accepts a client connection.
6. TimescaleDB records and retains a simulation run.
7. Engineering/historian queries work with populated graphs and recorded data.

No claim of a working one-command, fully seeded installation is made until these checks pass.
