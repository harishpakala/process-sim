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

Open the Vue UI at http://localhost:5176 and GraphDB Workbench at http://localhost:7201. The Python API is at http://localhost:8001. Database host port 5434 and OPC UA port 4841 are exposed to the host loopback only. Inside Docker, GraphDB uses port 7200 and TimescaleDB uses 5432.

Containers communicate through Docker DNS names (`api`, `graphdb`, `timescaledb`, `simulator`). The Vite development server proxies `/api` to `http://api:8001`. Data persists in named `graphdb_data` and `tep_timeseries` volumes.

**GraphDB initialization:** The `graphdb-init` one-shot service waits for GraphDB and creates repository `AAST` when missing. It does not overwrite an existing repository. Check `docker compose logs graphdb-init` and query `http://localhost:7201/repositories/AAST`. **Automatic engineering lifting:** The `semantic-lift` one-shot service runs after `graphdb-init`, executes `python -m semantic.template_lifting --push` and `python -m semantic.instance_lifting --validate --push` for the six configured domains, and uploads named RDF graphs to `AAST`. The API waits for successful completion. Check `docker compose logs semantic-lift` for failures. The shared `semantic_outputs` volume exposes generated DTWise catalogs and schema index to the API. GraphDB updates use `INSERT DATA` (duplicate RDF triples are not duplicated, but removed source assertions are not automatically deleted). This does not lift live TimescaleDB samples.

**Lifting verification:** Run `docker compose ps -a semantic-lift` and `docker compose logs --tail=100 semantic-lift`. Query the `AAST` repository to confirm the six engineering named graphs contain triples. If lifting fails, the API intentionally remains blocked rather than starting with incomplete engineering data. Re-running lifting adds assertions without clearing unrelated graphs. Changes to existing source values may leave stale triples until a separate graph replacement strategy is implemented.

**Historian setup:** TimescaleDB starts with database `tep_nexus`, but this Compose file does not yet validate historian schema migration or an end-to-end simulation recording. Confirm initialization and persistence before reporting benchmark results.

**GraphDB image:** The default is `ontotext/graphdb:10.8.0` as a starting configuration, not a verified distributable image. Override it with `GRAPHDB_IMAGE` if your licensed/available distribution uses another reference.

**Local development only:** The password fallback `1234` is not secure for production. Put a private `TEP_DB_PASSWORD` in an ignored `.env` file. No TLS or application authentication is configured. Do not expose the stack publicly.

## Stop

```sh
docker compose down
```

Volumes are preserved. **Do not run** `docker compose down -v` unless you intentionally want to erase local database volumes.

## Verification checklist (not yet executed)

1. `docker compose config` validates.
2. Images build and all five services start.
3. GraphDB `AAST` is created by `graphdb-init`; `semantic-lift` then generates, validates and publishes six engineering domains. Verify the named graphs and SHACL output.
4. UI `/api` calls reach the Python backend.
5. OPC UA simulator accepts a client connection.
6. TimescaleDB records and retains a simulation run.
7. Engineering/historian queries work with populated graphs and recorded data.

The automated semantic lifting service has not yet been exercised against a running GraphDB container. No claim of a working one-command, fully seeded installation is made until these checks pass.
