# ProductCatalog consolidation migration — 2026-10-23

Active ProductCatalog was reduced from 18 to 16 product records by removing three superseded sensors and adding the Endress+Hauser Cerabar PMP51B candidate. Original removed JSON records are archived in [superseded-product-catalog-records.json](superseded-product-catalog-records.json).

## Migration dependencies (not yet applied)

| Removed ProductCatalog idShort | AssetInventory signals still using the old ProductReference | Intended proposed replacement |
|---|---|---|
| SMC_PFMV505_1 | XMEAS1, XMEAS4, XMEAS5, XMEAS6, XMEAS10 | EandH_TMass_F300_Candidate (gas; sizing unverified) |
| SMC_PFMV505_1 | XMEAS2, XMEAS3, XMEAS14, XMEAS17 | EandH_Promass_F300_Candidate (liquid; sizing unverified) |
| SMC_PFMV505_1 | XMEAS19 | EandH_Prowirl_F200_Candidate (steam; sizing unverified) |
| SMC_PSE550 | XMEAS7, XMEAS13, XMEAS16 | EandH_PMP51B_Candidate (pressure; simulation family approved, ordering code pending) |
| IFM_LW2720 | XMEAS8, XMEAS12, XMEAS15 | EandH_FMR62B_Candidate (level; scaling/configuration pending) |

**Warning:** These 16 AssetInventory `ProductReference` values are now unresolved against the active ProductCatalog until the AssetInventory migration is completed. The `ProposedReplacementProductReference` fields added in earlier work remain distinct from active `ProductReference` fields; the migration must preserve previous references as provenance and not imply installed/engineering-approved status.

The temperature references `SMC_PSH_L2_01_W` and valve references `Siemens_S55264_V193` were already unresolved before this catalog consolidation. Their resolution is a separate AssetInventory migration.

## Catalog semantics

- Existing ECLASS class IRDIs for retained products are **unverified**, not new claims of authoritative ECLASS validation.
- No ECLASS IRDI or `semanticId` was invented for the new PMP51B candidate.
- ProductCatalog is a reference library, not proof of installed equipment or verified OPC UA mappings.
- All instrument families require per-signal engineering and measurement-semantic validation.

## Follow-up

1. Migrate AssetInventory active ProductReferences for the 16 affected signals and preserve original identifiers in a separate provenance field.
2. Resolve the five temperature and eleven valve references already missing from ProductCatalog.
3. Validate AAS schema/semantic lifting and run automated tests; this commit was not test-verified.
