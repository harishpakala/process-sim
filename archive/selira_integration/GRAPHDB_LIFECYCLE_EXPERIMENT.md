# SC-01 GraphDB snapshot lifecycle experiment

This is a **read-only**, snapshot-based integration. It queries the actual `ai:hasProductReference` and `pc:hasAssetIdentifier` predicates in explicitly named GraphDB graphs. It does **not** modify the GraphDB repository.

## 1. Capture revision R1

```bash
python -m selira_integration.lifecycle_cli capture \
  --endpoint http://localhost:7200/repositories/YOUR_REPOSITORY \
  --inventory-graph 'YOUR_INVENTORY_NAMED_GRAPH_IRI' \
  --catalog-graph 'YOUR_CATALOG_NAMED_GRAPH_IRI' \
  --revision R1 --output /tmp/selira-r1.json
```

Add `--catalog-complete` **only when the relevant catalog completeness has been independently established**. Without this flag, validation outcomes are INDETERMINATE.

## 2. Obtain revision R2

Apply a controlled engineering change to a **test GraphDB repository**, or use a separately versioned engineering graph. Do not change the production repository for the experiment.

Capture R2 with the same command and `--revision R2 --output /tmp/selira-r2.json`.

## 3. Compare and verify

```bash
python -m selira_integration.lifecycle_cli compare \
  --before /tmp/selira-r1.json --after /tmp/selira-r2.json \
  --history /tmp/selira-sc01-history.jsonl
```

This prints changed source values, affected assets, selective validation results, full baseline results, and assertions that the baseline agrees and unaffected results remain unchanged. The history file records initial results and pending/revalidation events. A new comparison run initializes its own state from R1; it is not a long-running lifecycle service.

## Tests

```bash
python -m unittest tests.test_selira_lifecycle_sc01 tests.test_selira_graphdb_snapshot -v
```

## Research and engineering limitations

- The current evaluator is a deterministic Python implementation of SC-01, **not selective pySHACL execution**.
- It covers assigned product references only; candidate references must not be promoted.
- Catalog completeness and engineering approval are external preconditions.
- A per-asset multiple-reference or per-product multiple-identifier ambiguity is rejected at snapshot ingestion.
- Snapshots record declared revision IDs; the adapter does not independently verify source revision provenance or guarantee consistent cross-graph reads under concurrent writes.
- Change detection covers the two SC-01 predicates only; contract revisions, catalog completeness changes, and other semantic dependencies require additional event sources.
- History is local JSONL, not yet immutable RDF/PROV-O persisted in GraphDB.
- These GitHub commits have not been executed against live GraphDB; run the tests and experiment in your environment before claiming empirical results.

**Next:** connect affected focus nodes to a native SHACL engine and persist revision-bound validation records in a dedicated provenance graph.
