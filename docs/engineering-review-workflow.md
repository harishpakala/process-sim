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

## Versioned physical BOM overlays

- `GET /api/engineering/physical-bom/revisions` lists immutable physical BOM revision snapshots and verifies each snapshot's SHA-256 digest.
- `POST /api/engineering/physical-bom/revisions` accepts `{"author":"Engineer","rationale":"Checked installation drawing","assignments":[{"bomItemId":"EBOM-XXXX","evidenceEventId":"<review event UUID>"}]}`.
- Each assignment must identify an **ECAD source item** whose exact EngineeringReference matches the candidate relationship's ECAD target. The evidence event must be the latest physical-membership decision for that relationship, explicitly approved and scoped to a valid named equipment assembly.
- An approval for functional correspondence **does not** authorize physical promotion. A physical installation approval **does not** assert that DEXPI and ECAD are the same installed device.
- The snapshot preserves the original canonical BOM unchanged and records each evidence event UUID and hash. A revision is an immutable overlay rather than an automatic source-data rewrite.
- The UI supports creating a one-assignment revision and inspecting historical revisions. API supports multiple assignments in one revision. Historical snapshots are not silently recomputed if a later approval is withdrawn; the reviewer must create a new revision and explicitly resolve prior membership.
- **Limitations:** Evidence documents are referenced but not stored or cryptographically checked. The model does not yet handle per-component serial numbers, installation points, quantity verification, supersession of whole BOM revisions, or a signed release workflow. SQLite admin-level tampering and removal of the entire DB are outside the current protections.

Run tests: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_engineering_reviews.py'` and `PYTHONPATH=src python -m unittest discover -s tests -p 'test_physical_bom.py'`.
