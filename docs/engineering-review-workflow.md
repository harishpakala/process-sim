# Engineering review persistence and physical membership evidence

The **Relationship Verification** page now uses the Python API rather than browser-local storage. Start the API with `PYTHONPATH=src python -m process_sim.api.server` and the frontend with `cd frontend && npm run dev`. Vite proxies `/api` to the Python server.

## Storage

- `GET /api/engineering/reviews` returns the full ordered event history and SHA-256 chain integrity status.
- `POST /api/engineering/reviews` appends a new event; existing decisions are never overwritten.
- SQLite file: `data/engineering_reviews.sqlite3` by default. Override with `PROCESS_SIM_REVIEW_DB` for a durable volume.
- Every event includes reviewer (self-declared), evidence reference, rationale, server timestamp, event ID, previous hash, and event hash. UPDATE/DELETE triggers prevent ordinary SQL modification.
- The hash chain detects accidental/unauthorized database row edits but **is not cryptographically tamper-proof** against a database administrator able to rewrite the entire chain. Backups, access controls, and independent hash anchoring are required for stronger audit assurances.
- Authentication is intentionally **not enabled**. Do not expose the API to an untrusted network. The server binds to `127.0.0.1` by default. Reviewer names are not verified identities.

## Physical membership evidence

A `PHYSICAL_MEMBERSHIP` event with `VERIFIED_PHYSICAL_MEMBERSHIP` requires an explicit equipment parent matching the candidate's equipment scope, a document/drawing reference, engineering rationale, reviewer and affirmative installation-evidence confirmation. It is a **separate reviewed claim** and does not automatically modify canonical EBOM `ParentItemId`, establish that DEXPI and ECAD refer to the same installed device, or determine procurement quantities.

The evidence reference is currently a **reference string**, not an uploaded or independently verified drawing. Reviewers must check the document and its revision outside the application. For production release, add document storage, versioning, signed approvals and a controlled workflow for applying accepted membership claims to a physical BOM revision.

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_engineering_reviews.py
PYTHONPATH=src python -m process_sim.api.server
cd frontend && npm run build
```

No migration from prior browser-local decisions is automatic; export legacy reviews before upgrading if they need preservation.
