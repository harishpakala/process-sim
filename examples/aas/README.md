# TEP NEXUS AAS files

**Canonical runnable directory:** `examples/aas/`. This folder holds the DEXPI, ECAD, AssetInventory, ProductCatalog, engineering BOM, and OPC UA templates and the available instance files. `semantic/templates/` remains temporarily as a legacy compatibility location; do not independently edit its copies. Full removal requires checking every generator/importer that refers to those paths.

## Identifier contract

- DEXPI / ECAD: `AssetIdentifier` denotes the canonical logical asset; `LocalId` denotes the representation-specific local identifier.
- AssetInventory: `AssetIdentifier` denotes the asset, `ProductIdentifier` refers to a ProductCatalog entry, and `OperationalReference` refers to a measurement signal. `EquipmentTag` is retained.
- ProductCatalog: `ProductIdentifier` denotes the product type; there is no `AssetIdentifier`.
- The current JSON migration **renames fields without asserting that existing DEXPI, ECAD and inventory URI values are identical**. `tep_dexpi_ecad_reconciliation.json` contains candidate correspondences with `identityConfirmed: false`; do not rewrite these as verified identity mappings without an explicit simulation-model decision.
- Existing `CandidateProductReference` and `InstalledProductReference` convey provisional-versus-installed semantics and are not interchangeable with `ProductIdentifier`.

## Validation

From repository root:

```sh
python scripts/test_tep_nexus_identifiers.py
python scripts/validate_asset_inventory_semantics.py
```

Regenerate/reload GraphDB after migrating the RDF import pipeline; changing JSON does not modify a running GraphDB repository. Existing saved evaluation JSON files contain old property labels and should be regenerated.

## Compatibility

`semantic/templates/` and `examples/aas/` previously contained overlapping templates. New code should read `examples/aas/`; legacy references can be removed after dependent code and workflows have been updated. BOM remains available as data but is not required in the initial Q1–Q10 cross-domain benchmark.
