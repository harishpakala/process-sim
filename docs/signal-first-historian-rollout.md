# Signal-first Historian deployment and verification

The signal-first historian API and UI are committed on the feature branch, but a Git commit **does not apply** a database migration or deploy the service. Run these steps against the intended environment after reviewing database access and backup policy.

## 1. Apply metadata migration

Run `scripts/sql/20261122_signal_metadata.sql` against the same PostgreSQL/TimescaleDB database configured by `TEP_TIMESCALE_DSN`. The migration creates `public.signal_metadata` and inserts known signal identifiers as `Unclassified`; it does not modify the `signal_samples` hypertable or assign unsupported units.

Verify:

```sql
SELECT measurement_type, COUNT(*) FROM public.signal_metadata GROUP BY measurement_type;
SELECT COUNT(DISTINCT signal_id) FROM public.signal_samples;
SELECT COUNT(*) FROM public.signal_metadata;
```

New signals ingested after migration are still visible in discovery via the left join and default to `Unclassified` in API responses. To persist metadata for new signals, rerun the migration's idempotent `INSERT ... ON CONFLICT DO NOTHING` statement or add an ingestion-time metadata upsert. Classifications should be populated only from a documented authoritative source; keep `verification_status = 'NOT_VERIFIED'` until reviewed.

## 2. Validate the backend

With the project's Python dependencies installed:

```bash
python -m unittest discover -s tests -p test_signal_historian.py
```

Start the API with `TEP_TIMESCALE_DSN` configured. Query:

```text
GET /api/ai/vtkg/historian/runs
GET /api/ai/vtkg/historian/measurement-types
GET /api/ai/vtkg/historian/signals?run_id=<UUID>
GET /api/ai/vtkg/historian/signals?run_id=<UUID>&measurement_type=Unclassified
POST /api/ai/vtkg/historian/signal-values
  {"run_id":"<UUID>","signal_id":"XMEAS9","start_simulation_seconds":null,"end_simulation_seconds":null}
```

Confirm the direct endpoints work **without** `GRAPHDB_SPARQL_ENDPOINT` configured. The retrieval endpoint returns at most 5,000 samples and marks truncation; narrow the time window if necessary.

## 3. Validate frontend

```bash
cd frontend
npm ci
npm run build
```

Check that the historian form has no DEXPI/ECAD or LocalID requirement, that Measurement Type filters SignalNames, and that the chart displays direct historian results.

## 4. Verify on-demand knowledge explorer

Configure `GRAPHDB_SPARQL_ENDPOINT` only for the knowledge exploration path. Select a SignalName with an existing DEXPI or ECAD association, retrieve the historian data, then click **Explore engineering knowledge & R01–R05**. Confirm that the VTKG evidence and mapping candidates correspond to the selected signal. Try an unmapped signal and confirm that the historian chart remains available while the explorer reports an unresolved mapping.

## Known limitations

- Asset Inventory and Product Catalog source-backed joins are not implemented; the bridge must continue to report `NOT_RESOLVED`.
- A shared AssetIdentifier is semantic evidence, **not** proof of physical sensor identity.
- Existing R01–R05 operators are engineering-function-oriented; the explorer chooses a deterministic primary source-backed mapping and reports all candidates. Further work is needed to support ambiguous mappings as first-class choices.
- No live migration, deployment, end-to-end browser run, or CI build has been performed as part of these commits.
