# GraphDB AAS Knowledge Graph

GraphDB SPARQL repository (local development): `http://localhost:7200/repositories/AAS`.

**AssetInventory** (asset explorer, search, counters, status details, product links and graph) and **ProductCatalog** (product explorer, details and graph) now query RDF via SPARQL. Neither component reads bundled AAS JSON. The KG is the sole UI data source.

## Required deployment

1. Confirm GraphDB has a repository with ID **AAS**.
2. Import `examples/kg/tep_asset_product_graph.ttl` into **AAS**. The repository must include `https://example.org/tep/kg/ProductType` product resources and `https://example.org/tep/kg/vocab/hasAssetInventoryStatus` status edges.
3. Run `npm run dev` in `frontend/`. The Vite dev proxy routes `/kg/repositories/AAS` to `http://localhost:7200/repositories/AAS`. If GraphDB runs on a different host, set `GRAPHDB_URL` to its origin (for example `http://pakala:7200`) before starting Vite.
4. For deployed/production frontends, configure a reverse proxy with the same `/kg` route. The Vite dev proxy does not apply to production builds. Alternatively set `VITE_KG_SPARQL_ENDPOINT` to an accessible SPARQL endpoint with appropriate CORS support.

Do not put GraphDB credentials in frontend environment variables. If the RDF has not been imported, a reachable repository will return no product/status resources. If the reverse proxy or repository is absent, the UI shows a request error instead of substituting JSON.

GraphDB connectivity, repository content, and the frontend build have **not been verified** in the target environment. The RDF is generated from static research examples; querying it is not equivalent to real-time runtime synchronization.
