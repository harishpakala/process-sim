# Multi-contract extension: initial source audit

Baseline: `66d81732d088d4e092b2fdce3f80d81864e8264a`.

## Candidate scope

Reuse historical EngineeringCorrespondence SC-02 (quantity-kind agreement), SC-03 (unit compatibility), and SC-04 (configuration/revision applicability). Historical YAML SC-04 instead specifies operating-envelope coverage; these are distinct definitions. No new SAFSL definitions or compiler features are introduced by this audit.

## Source observations

- `semantic/ontology2/dexpi-instance.ttl`: measured-variable properties include empty lexical values with explicit QUDT semantic identifiers on AAS property resources (e.g. MassFlowRate and Power). Annotation is not a populated measurement value or proof of correspondence.
- Product catalog template and instance include technical quantity-kind/unit metadata and candidate qualification notes. Asset inventory has product identifiers and unverified configuration notes.
- OPC UA connectivity contains provisional engineering matches and explicit unverified live binding notes. ECAD has device types/descriptions.
- Engineering BOM template defines revision; instance retrieval did not return usable content. Revision applicability cannot be established from this audit.
- `src/process_sim/backends/tep/mapping.py`: units for 41 measurements, including XMEAS7 kPa gauge. `signal_asset_unit.py` already checks the proposed XMEAS7 / PI-1101 / PMP51B candidate, pressure reference, QUDT unit and quantity kind, and external verification flags. `unit_validation.py` supports a restricted multiplicative QUDT registry; historical SC-03 supports a different symbol registry with offsets. Reconcile semantics explicitly, including gauge/absolute conventions and HTTP/HTTPS QUDT identifiers, before reuse.
- `scripts/sql/20261122_signal_metadata.sql`: classification/unit schema and verification status; migration does not establish populated verified metadata. No live database queried.

## Next steps

1. Verify exact joins and source provenance for the XMEAS7 candidate, then other signals; quantify eligible populations and missing evidence.
2. Define SC-02 canonical quantity-kind comparison and SC-03 unit/convention compatibility with explicit supported vocabulary and unknown handling. Do not infer identity or authority from compatibility.
3. Decide whether SC-04 is a graph contract or qualification-context condition after auditing revision evidence. Preserve distinct historical meanings.
4. Extend grammar, reference semantics, compilation and manager only after binding and evidence requirements are established.

This is an initial static audit, not a complete RDF population analysis, live verification or test run.

## DTWISE schema index and mapping provenance (source review)

Source directory: `semantic/ontology2/dtwise/`.

- `dtwise-schema-index.json` indexes 424 concepts (31 classes, 224 shapes, 169 properties), 461 relationships, 198 SHACL shape paths and 18 ontology edges across the six AAS domains. It has token postings for measured, pressure, quantity, qudtquantity, qudtunit and revision. Its embedded diagnostics report zero verified mappings and `No verified mapping source was supplied; no joins inferred.` **This diagnostic describes the index build, and conflicts with the separate approved registry if interpreted as current global status.**
- `cross-domain-mapping-candidates.json` has 13 proposals, all `verified: false`; mostly shared-identifier property names supported by SHACL schema structure, not owner-pair proofs.
- `cross-domain-mappings.json` has the same 13 identifiers marked `verified: true`, with explicit domain-owner approval of shared key semantics and evidence relationship IDs. It covers ten AssetIdentifier pairings and three ProductIdentifier pairings. Registry notes mostly disclaim independent instance-level testing. Property-level mapping approval is not automatically a verified value match, authenticated engineering assertion, or authorization for use.
- No listed mapping directly equates DEXPI measurement quantity kind to product technical quantity kind, TEP engineering unit to catalog unit, or establishes a revision-applicability relation. Existing 13 mappings are a **join-key foundation**, not complete SC-02/SC-03/SC-04 definitions.
- Exact QUDT namespace normalization, quantity-kind equivalence rules, measurement basis, mass/volume and percent/length conversions, and authoritative revision evidence remain outstanding. Prior JSON instance audit found 22 DEXPI measurement functions with unique inventory/OPCUA/product value matches, but these are observations and do not resolve mapping-evidence caveats.

### Recommended separation

1. Retain the immutable candidate register and owner-approved key register, and record registry revision/provenance in any contract evaluation context.
2. Use approved keys only to construct candidate focus/link populations. Check uniqueness and actual values against a consistent instance snapshot. Report conflicts, missing evidence and changing coverage explicitly.
3. Evaluate SC-02 quantity kinds and SC-03 units using independent explicit semantics and trusted attestations; treat unsupported conversions as U, not successful matches.
4. Model SC-04 configuration/revision applicability as context-sensitive unless required versioned source facts can be bound and qualified. `UNSPECIFIED` BOM revisions cannot yield a positive assessment.
5. Rebuild the schema index with the approved registry as a declared input, or document diagnostics as index-build provenance rather than a live global mapping count; do not silently change the original artifacts.

No compiler or manager changes, independent authentication, or post-commit test run are implied by this audit.
