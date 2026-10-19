# AAS-first ECLASS and QUDT semantic modeling contract

Status: proposed implementation contract (no unverified ECLASS identifiers or physical units assigned).

## Authority and identity

- Product Catalog AAS: authoritative product model/classification and manufacturer-rated technical specifications.
- Asset Inventory AAS: authoritative installed-asset identity, product reference, configuration, limits, and operational references.
- AAS SubmodelElements carry semanticId for their defined concepts; use supplementalSemanticIds only for legitimately additional interpretations, not presumed equivalence.
- Preserve original external semantic references, including ECLASS release/version. Asset instance IDs must never be replaced by class identifiers.
- GraphDB contains a derived RDF projection of AAS, not an independently maintained replacement for its engineering semantics.
- TimescaleDB remains the historian. The signal's interpretation comes from the AAS-derived semantic graph.

## Technical specification model

Each technical specification must distinguish:
1. Specification identity and owner (product type or installed asset).
2. ECLASS property semantic identifier (verified from a named ECLASS release).
3. Value type and value, or min/max for a range.
4. Unit definition, and verified mapping to a QUDT unit IRI.
5. Quantity kind, mapped to QUDT only when physically justified.
6. Source, revision, evidence, and applicability (manufacturer rating vs installed configuration vs operating limit).
7. Verification status (verified, pending, unresolved).

Product classification and property semantic identifiers are distinct concepts. A product may support a measurement range that does not match the installed asset's operating envelope.

## RDF lifting rules

| AAS source | Required lifted representation |
| --- | --- |
| AAS SubmodelElement identity | Stable RDF resource and original AAS element path |
| semanticId external key | Exact source identifier retained as an RDF reference |
| supplementalSemanticIds | Retained individually, without automatic owl:sameAs |
| Product ECLASS classification | Class reference separate from instance identity |
| Technical property ECLASS ID | Property concept reference on property resource |
| Typed Property or Range | Value and explicit range boundaries; preserve original datatype |
| Unit/quantity metadata | QUDT unit and quantity-kind references only after verification |
| ProductReference | Explicit product-to-installed-asset relationship |
| OperationalReference | Link to signal definition; do not infer physical unit from signal name |
| Source revision | Provenance for every mapping and enrichment |

Do not assert equivalence between ECLASS and QUDT concepts without an explicit, reviewed mapping. Never fabricate ECLASS IRDIs, QUDT units, or manufacturer specifications.

## Current code gaps to address

- `semantic/templates/product_catalog_template.json` has a repeatable `TechnicalProperty` collection, but no required property-specific semantic identifier, unit, quantity kind, provenance, or verification status.
- `semantic/templates/asset_inventory_template.json` has `ProductReference` and `OperationalReference` as string properties; installed configuration and operating limits are not yet represented as semantically typed specifications.
- `semantic/instance_lifting.py` currently lifts Property values as direct literals, plus an AAS Property resource. It does not yet expose the complete technical specification as a typed value/unit/quantity structure.
- `semantic/template_lifting.py` generates SHACL structural shapes, but no cross-standard checks for ECLASS/QUDT semantic completeness.
- `docs/semantic/PRODUCT_CATALOG_ENGINEERING_AUDIT.md` records real product compatibility concerns; classification must not be interpreted as suitability approval.

## Implementation order

1. Inventory the actual AAS instances and verify their existing element shapes and identifiers.
2. Add backwards-compatible AAS technical-specification elements and explicit classification references.
3. Add a versioned, reviewed ECLASS-to-QUDT mapping registry with evidence and status.
4. Extend template and instance lifting to preserve all semantic references and provenance.
5. Add SHACL checks for required identifiers, supported unit mappings, typed ranges, and unresolved semantics.
6. Expose a GraphDB-backed semantic metadata API and use it for replay labels and units.

## Acceptance criteria

- A product specification and its corresponding installed-asset configuration are distinguishable and traceable to source AAS paths.
- Original ECLASS identifiers survive round-trip inspection of the lifted RDF.
- QUDT mappings can be inspected with their provenance and validation status.
- Unknown units are displayed as unspecified, never silently guessed.
- Existing historical replay and asset-history queries remain functional.
