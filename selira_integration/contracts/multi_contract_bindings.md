# Candidate referential integrity contracts

SC-02, SC-03 and SC-04 reuse the existing uniqueness grammar and compiler. They are distinct from historical correspondence contracts. The proposed engineering policy is that each assigned identifier resolves to exactly one canonical target resource. Owner-approved DTWISE key semantics support the joins, not the cardinality policy or instance authority.

| Contract | Focus | Target | Preliminary matches |
|---|---|---|---:|
| SC-02 | DEXPI AssetIdentifier subjects (5 equipment, 22 instrumentation, 12 actuating) | Asset | 39/39 |
| SC-03 | OPC UA AssetIdentifier subjects | Asset | 34/34 |
| SC-04 | BOM ProductIdentifier subjects | Product | 71/71 |

SC-02 and SC-03 counts are static inspections of generated RDF Turtle statements; SC-04 uses 71 assigned BOM items from AAS JSON against RDF catalog (79 items, 22 assemblies, 8 unassigned items). The large BOM RDF was not retrievable; verify with RDFLib locally. The V2 BOM template ID is grounded in engineeringbom-template.ttl. No data changes.

All bindings use predicate focus and lexical matching, as SC-01. The compiler requires a focus class even in predicate mode; SC-02 uses InstrumentationFunction as a placeholder for this required field, NOT the complete focus population. The existing manager's single-class guard is incompatible with mixed DEXPI classes and must not be used for SC-02 unchanged. SC-04 uses BOMItemRecord, as defined in the RDF template. Confirm predicate subjects and root membership locally, including empty or multivalued identifiers. Unassigned records are excluded only under confirmed applicability policy. No runtime completeness or identity attestations are supplied. Compiler diagnostic text still says product for asset targets; semantics are unchanged.

Candidate artifacts only; no compilation, SHACL execution, or admission verification yet.
