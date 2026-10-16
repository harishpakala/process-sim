# AssetInventoryStatus Knowledge Graph

The AssetInventory **Knowledge graph** tab queries a GraphDB SPARQL endpoint. It does **not** reconstruct graph nodes from the AAS JSON snapshot. The inventory list still uses its existing offline JSON data for selecting an asset; the graph detail itself comes exclusively from SPARQL results.

## Setup

1. Start GraphDB and create a repository named `tep` (or configure your endpoint accordingly).
2. Import `examples/kg/tep_asset_product_graph.ttl` into that repository.
3. Run the frontend in development with `npm run dev` from `frontend/`. Vite proxies `/kg/repositories/tep` to `http://localhost:7200/repositories/tep`. Set `GRAPHDB_URL` when GraphDB runs elsewhere.
4. For a deployed frontend, configure a same-origin proxy to GraphDB and set `VITE_KG_SPARQL_ENDPOINT` if its path differs from `/kg/repositories/tep`. The endpoint must return SPARQL JSON results and permit browser access (or use the proxy). Do not put credentials in Vite environment variables.

The KG export is reproducible using `python3 scripts/export_asset_kg.py` and includes dedicated status resources connected with `tep:hasAssetInventoryStatus`. The KG UI also queries `tep:hasProductType` and `tep:hasOperationalSignal`. Status values are static research placeholders until runtime integration is implemented.

No GraphDB service was started or queried as part of this repository update; a running repository and frontend build remain to be verified.
