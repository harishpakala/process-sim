# ECLASS classification audit (updated 2026-10-23)

## Current ProductCatalog

- **20 active product records; 20/20 have nonempty** `ECLASSClass`, `ECLASSPreferredName`, and `ECLASSIRDI`.
- Two non-product placeholders, `Unspecified_MotorDrive_Reference` and `Unspecified_AgitatorDrive_Reference`, were removed from the active catalog and archived at `docs/migrations/retired-product-catalog-placeholders.json`.
- The ProductCatalog SHACL template was **not relaxed** to make classification optional.
- The user reported successful GraphDB graph updates and successful SHACL validation after these changes. This is a reported validation result; the GraphDB validation report has not been archived here.
- Source-level cross-reference check: all 38 populated `ProductReference` fields in the 62-asset AssetInventory resolve to current ProductCatalog `AssetIdentifier` values. See `docs/migrations/asset-product-graphdb-verification.md` for query procedures.

## Verification limitations

**Populated ECLASS fields and SHACL conformance do not establish official ECLASS correctness.** User-supplied classification details were matched technically to candidate equipment; some older classifications and two family-level classifications were inherited from related catalog entries. The official ECLASS release, language, preferred names, codes and IRDIs have **not all been independently authenticated**. See each catalog entry's `ECLASSClassificationBasis` and `ECLASSVerificationStatus` when present.

In particular, the ABB Process Performance family is classified as a **low-voltage three-phase asynchronous motor**, conditional on the actual selected motor being a low-voltage three-phase variant. Do not replace this with a synchronous or DC motor class without product evidence.

The KSB Multitec family uses the broader **centrifugal pump** class; actual pump duty, NPSH, stage count, motor sizing and selection remain engineering decisions.

Official ECLASS lookup: https://eclass.eu/en/eclass-standard/search-content

## Reproducibility

```bash
python3 -m unittest discover -s tests -p 'test_aas_catalog_inventory_contract.py'
python3 scripts/import_knowledge_graph.py --validate
```

The first command checks the source JSON contract; the second lifts configured AAS domains and validates their RDF against generated SHACL shapes. Neither certifies the official AAS metamodel or engineering product suitability. GraphDB SPARQL queries and expected counts are documented in `docs/migrations/asset-product-graphdb-verification.md`.
