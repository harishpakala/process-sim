# GraphDB access through the Python API

All Vue knowledge-graph components call `selectTriples()` in
`frontend/src/lib/sparql.ts`. That helper now sends JSON POST requests to
`/api/kg/select`, rather than calling GraphDB directly.

## Local startup

From the repository root (with the package installed or `PYTHONPATH=src`):

```bash
# Terminal 1
PYTHONPATH=src python -m process_sim.api.server

# Terminal 2
cd frontend
npm install
npm run dev
```

On Windows PowerShell use `$env:PYTHONPATH="src"` before running the API.

The Python API defaults to `http://127.0.0.1:8000`; Vite proxies `/api`
to that address. Configure `PROCESS_SIM_API_URL` for a different API address.

The Python API connects to GraphDB using
`GRAPHDB_SPARQL_ENDPOINT` (default
`http://localhost:7200/repositories/AAS`). This setting is no longer
exposed to the browser.

`GET /api/health` reports whether the Python API is running, **not**
whether GraphDB is available. `POST /api/kg/select` accepts
`{"query":"SELECT ?s ?p ?o WHERE { ... }"}` and returns SPARQL JSON bindings.
GraphDB errors are returned as JSON errors with HTTP 502.

## Security and scope

The API binds to loopback by default. It is a development integration bridge,
not a hardened public SPARQL service. The current query checks reject common
SPARQL update verbs but are not a full SPARQL parser or security boundary.
Do not expose this endpoint to untrusted users without authentication,
authorization, query restrictions, and resource limits. Prefer dedicated
backend endpoints for domain-specific operations as the platform matures.

The Python semantic import scripts still access GraphDB directly as backend
tools. This migration removes **browser-side** GraphDB access; it does not
change the backend ingestion workflow.
