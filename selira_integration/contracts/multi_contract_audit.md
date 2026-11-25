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
