# ProductCatalog / AssetInventory GraphDB verification (2026-10-23)

## Current evidence and scope

- User reported GraphDB graph update succeeded and SHACL validation passed for the updated graphs. No validation report or query results are attached to this repository yet.
- Source JSON audit: 20 ProductCatalog records, all with `ECLASSClass`, `ECLASSPreferredName`, `ECLASSIRDI`; 62 AssetInventory records, 38 populated `ProductReference` values, all 38 resolve to a ProductCatalog `AssetIdentifier`.
- The other 24 assets are **not all missing product selections**: five simulated equipment records have separate provisional `CandidateProductReference` fields; 19 are logical XMEAS23–XMEAS41 measurements with no physical product reference.
- The five simulated equipment candidates are TEP_Reactor (REQUIRES_ALTERNATIVE), TEP_Condenser, TEP_Separator, TEP_Compressor, TEP_Stripper (four PROVISIONAL_CANDIDATE). Do not silently promote candidate references into approved ProductReference values.
- No official ECLASS-release or AAS metamodel certification is asserted.

## SPARQL queries

The lifting implementation in `semantic/instance_lifting.py` emits domain predicates `has<idShort>` with direct literal values. The `ProductReference` and `AssetIdentifier` values are URI-shaped **literals**, not explicit RDF resource links. Join by literal equality; do not assume `owl:sameAs` or direct object relationships.

**1. Cross-domain asset → product → ECLASS lookup (expect 38 rows with current source data):**

```sparql
PREFIX ai: <https://example.org/assetinventory/>
PREFIX pc: <https://example.org/productcatalog/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?assetLabel ?productLabel ?productRef ?eclassCode ?eclassName ?irdi
WHERE {
  ?asset ai:hasProductReference ?productRef ;
         rdfs:label ?assetLabel .
  ?product pc:hasAssetIdentifier ?catalogIdentifier ;
           pc:hasECLASSClass ?eclassCode ;
           pc:hasECLASSPreferredName ?eclassName ;
           pc:hasECLASSIRDI ?irdi ;
           rdfs:label ?productLabel .
  FILTER(STR(?productRef) = STR(?catalogIdentifier))
}
ORDER BY ?assetLabel
```

**2. Detect dangling ProductReference literals (expect zero rows):**

```sparql
PREFIX ai: <https://example.org/assetinventory/>
PREFIX pc: <https://example.org/productcatalog/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?assetLabel ?productRef
WHERE {
  ?asset ai:hasProductReference ?productRef ;
         rdfs:label ?assetLabel .
  FILTER NOT EXISTS {
    ?product pc:hasAssetIdentifier ?catalogIdentifier .
    FILTER(STR(?productRef) = STR(?catalogIdentifier))
  }
}
ORDER BY ?assetLabel
```

**3. Assets without selected ProductReference (expect 24 rows):**

```sparql
PREFIX ai: <https://example.org/assetinventory/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?assetLabel ?assetType ?candidateRef ?candidateStatus
WHERE {
  ?asset ai:hasAssetId ?assetId ;
         rdfs:label ?assetLabel .
  OPTIONAL { ?asset ai:hasAssetType ?assetType }
  OPTIONAL { ?asset ai:hasCandidateProductReference ?candidateRef }
  OPTIONAL { ?asset ai:hasCandidateSelectionStatus ?candidateStatus }
  FILTER NOT EXISTS { ?asset ai:hasProductReference ?selectedRef }
}
ORDER BY ?assetLabel
```

**4. Catalog entries missing ECLASS fields (expect zero rows):**

```sparql
PREFIX pc: <https://example.org/productcatalog/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?productLabel
WHERE {
  ?product pc:hasAssetIdentifier ?identifier ;
           rdfs:label ?productLabel .
  FILTER (
    NOT EXISTS { ?product pc:hasECLASSClass ?code } ||
    NOT EXISTS { ?product pc:hasECLASSPreferredName ?name } ||
    NOT EXISTS { ?product pc:hasECLASSIRDI ?irdi }
  )
}
ORDER BY ?productLabel
```

**5. Specific motor lookup (verify expected ABB family):**

```sparql
PREFIX ai: <https://example.org/assetinventory/>
PREFIX pc: <https://example.org/productcatalog/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?assetLabel ?productLabel ?code ?name
WHERE {
  ?asset rdfs:label ?assetLabel ;
         ai:hasProductReference ?ref .
  FILTER(?assetLabel IN ("TEP_M_1301", "TEP_M_1401", "TEP_M_1501"))
  ?product pc:hasAssetIdentifier ?identifier ;
           pc:hasECLASSClass ?code ;
           pc:hasECLASSPreferredName ?name ;
           rdfs:label ?productLabel .
  FILTER(STR(?ref) = STR(?identifier))
}
```

**Important:** Queries above use the default dataset union available to the GraphDB query endpoint. If the repository's default dataset excludes named graphs, configure the query dataset to include the instance named graphs or wrap patterns in `GRAPH ?g { ... }` blocks with separate graph variables for each domain. Check `semantic/ontoutils.py` for the namespace bindings and deterministic named graph URI convention.

## Regression procedure

```bash
python3 -m unittest discover -s tests -p 'test_aas_catalog_inventory_contract.py'
python3 scripts/import_knowledge_graph.py --validate
```

The first command checks source JSON contract only and requires Python standard library. The second performs RDF lifting and local SHACL validation for **all configured domains**; it requires project dependencies and is not a substitute for official AAS metamodel validation. Do not use `--push` unless you intentionally want to overwrite the configured GraphDB named graphs.

For each query, record the GraphDB repository, timestamp, result count, and any failures. Expected counts are baselines for this source revision, not proof of a live query result. Attach exported SHACL report when available.
