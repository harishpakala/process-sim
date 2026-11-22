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

## 5. Populate provisional measurement types from live LocalIDs

The LocalID convention is `T=Temperature`, `P=Pressure`, `L=Level`, `F=Flow`, `J=Energy`. Classification is based on GraphDB DEXPI/ECAD LocalID mappings joined to OPC UA SignalNames; it is a **provisional engineering inference**, not a verified physical sensor or unit.

If the initial metadata migration has not run, apply `scripts/sql/20261122_signal_metadata.sql`. If it **already ran**, additionally apply `scripts/sql/20261122_signal_metadata_flow_upgrade.sql` to add Flow to the existing constraint.

From the repository root, with the Python environment and both `TEP_TIMESCALE_DSN` and `GRAPHDB_SPARQL_ENDPOINT` configured:

```bash
python -m unittest discover -s tests -p 'test_classify_historian_signals.py'
python -m scripts.classify_historian_signals
# Review the JSON proposals, especially conflicting and unmapped signals.
python -m scripts.classify_historian_signals --apply
```

The script writes only consistent inferred types, with `classification_source='GraphDB DEXPI/ECAD LocalID prefix heuristic'` and `verification_status='PROVISIONAL'`. It does not overwrite already classified or verified metadata, does not invent units, and does not modify the observation hypertable.

Inspect results:

```sql
SELECT signal_id, measurement_type, unit, classification_source, verification_status
FROM public.signal_metadata ORDER BY signal_id;
```

Any signals without a consistent supported LocalID remain Unclassified. The actual database has not been accessed by these repository commits.

## 6. DEXPI actuating and instrumentation join and audit evidence

The live DEXPI discovery now includes both `dexpi:InstrumentationFunction` and `dexpi:ActuatingFunction`, reading their `dexpi:hasLocalId` and `dexpi:hasAssetIdentifier` and joining to `opcua:hasAssetIdentifier` / `opcua:hasSignalName`. **The verified repository mapping is OPCUAConnectivity; an OPCUAINVENTORY schema and its predicates have not yet been verified.** Do not rename the source or claim an inventory join without inspecting the actual dataset.

Before running `--apply`, apply `scripts/sql/20261122_signal_engineering_evidence.sql` to persist every mapped LocalID and AssetIdentifier separately from the classification row. Existing databases also require the Flow constraint upgrade described above. The classifier's `--apply` now writes source-backed rows to `signal_engineering_evidence` and updates only consistent, previously unclassified metadata to PROVISIONAL.

Inspect evidence with:

```sql
SELECT e.signal_id, e.engineering_domain, e.local_id, e.asset_identifier,
       e.inferred_measurement_type, m.measurement_type, m.verification_status
FROM public.signal_engineering_evidence e
LEFT JOIN public.signal_metadata m ON m.signal_id = e.signal_id
ORDER BY e.signal_id, e.engineering_domain, e.local_id;
```

ActuatingFunction LocalIDs without supported measurement prefixes remain evidence-only. No live GraphDB query, SQL migration, or classifier run has been executed by these commits.
