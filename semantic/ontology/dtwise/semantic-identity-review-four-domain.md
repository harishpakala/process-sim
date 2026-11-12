# Semantic identity review — four-domain asset identifier join

**Review ID:** `review/asset-identity-four-domain-001`  
**Mapping ID:** `engineeringbom_ecad_dexpi_assetinventory_asset_identifier`  
**Decision:** **PENDING — NOT APPROVED**  
**Catalog status:** `candidate_pending_semantic_approval`  
**Prepared:** 2026-11-12  
**Reviewer / decision authority:** To be assigned  
**Evidence repository:** GraphDB repository `AAS`; committed baseline `semantic/ontology/dtwise/four-domain-graphdb-baseline.json`

## 1. Proposed mapping and scope

Candidate comparison: `STR(?id0) = STR(?id1) = STR(?id2) = STR(?id3)` over the respective `hasAssetIdentifier` values. This is a **literal-string equality join**, not an OWL identity assertion, and does not imply `owl:sameAs`.

The proposed scope is limited to the explicitly cataloged EngineeringBOM, ECAD, DEXPI, and AssetInventory SHACL paths. No inference is permitted from other identifier properties, similar names, or transitive joins.

| Domain | Selected entity | SHACL-grounded traversal to identifier | Semantic question requiring owner confirmation |
| --- | --- | --- | --- |
| EngineeringBOM | BOM item record | `hasBOMItems → hasBOMItemRecord → hasAssetIdentifier` | Does each record refer to a physical asset, a design position, or a revision-specific BOM item? |
| ECAD | Device | `hasDevices → hasDevice → hasAssetIdentifier` | Is the value an asset tag, device designation, or project-scoped reference? |
| DEXPI | Actuating function / equipment / instrumentation function | `hasActuatingFunctions → hasActuatingFunction → hasAssetIdentifier`; **or** `hasEquipments → hasEquipment → hasAssetIdentifier`; **or** `hasInstrumentationFunctions → hasInstrumentationFunction → hasAssetIdentifier` | Do these three object types all use the same asset-identity namespace and scope? |
| AssetInventory | Asset | `hasAssets → hasAsset → hasAssetIdentifier` | Does the value identify the same asset as the engineering and design identifiers? |

All predicate IRIs in these paths use their corresponding `https://example.org/<domain>/` namespaces as recorded in the mapping catalog. The existence of a SHACL path establishes structural grounding, **not** semantic equivalence.

Do **not** substitute AssetInventory `hasProductIdentifier`, `hasRelatedAssetIdentifier`, or `hasSourceAssetIdentifier` for its own `hasAssetIdentifier`. Likewise, DEXPI local, source, or related identifiers are not approved identity substitutes.

## 2. Reproducible technical evidence (observed)

The following is confirmed by the existing GraphDB baseline and user-executed live integration check on 2026-11-12:

| Check | Observed |
| --- | ---: |
| Distinct projected result rows | 68 |
| Shared identifier strings | 34 |
| Distinct EngineeringBOM records | 68 |
| Distinct ECAD devices | 34 |
| Distinct DEXPI objects | 34 |
| Distinct AssetInventory assets | 34 |
| EngineeringBOM rows per shared identifier | 2 |
| Live baseline validator failures | 0 |
| Automated `test_dtwise*.py` tests | 109 passed |

**Interpretation boundary:** These results show repeatable data-level string equality for the current dataset. They do not prove the identifiers are globally unique, stable across revisions, or semantically identical across all four domains.

The 2:1 EngineeringBOM-record-to-shared-identifier relationship requires an owner explanation. It could be legitimate multiple records for one asset, but **no cause is established by the counts alone**.

Reproduce:

```powershell
python -m unittest discover -s tests -p "test_dtwise*.py" -v
python -m semantic.dtwise_graphdb_integration --endpoint "http://localhost:7200/repositories/AAS"
```

The live runner intentionally opts into candidate execution. The ordinary compiler must reject this four-domain mapping without `--allow-candidate` while approval remains pending.

## 2a. Ontology-level findings from committed templates (2026-11-12)

The four source templates were reviewed directly in `semantic/ontology/`. These are source-derived observations, not semantic approval.

| Domain | Source property definition | SHACL cardinality | Source file |
| --- | --- | --- | --- |
| EngineeringBOM | `owl:DatatypeProperty` with label `AssetIdentifier`; no descriptive `rdfs:comment` on the property | `sh:minCount 0`, `sh:maxCount 1` | `engineeringbom-template.ttl` |
| ECAD | “Identifier associated with the represented asset.” | `sh:minCount 1`, `sh:maxCount 1` on Device | `ecad-template.ttl` |
| DEXPI | “Identifier associated with the represented engineering asset.” | `sh:minCount 1`, `sh:maxCount 1` on ActuatingFunction, Equipment and InstrumentationFunction | `dexpi-template.ttl` |
| AssetInventory | “Identifier of the asset represented by this inventory record.” | `sh:minCount 0`, `sh:maxCount 1` | `assetinventory-template.ttl` |

**Interpretation:** The descriptions are compatible with an asset-identifier association, but do not prove that all domains refer to an identical asset referent. No common issuing authority, global uniqueness guarantee, cross-domain equivalent-property axiom, or governed normalization rule was established from these property definitions. Per-record maximum cardinality does not guarantee uniqueness across records and does not explain the observed two-BOM-record multiplicity.

DEXPI explicitly defines `hasRelatedAssetIdentifier` as the identifier of a *related* asset, not necessarily the object's own; AssetInventory explicitly distinguishes `hasProductIdentifier` from its own `hasAssetIdentifier`. Neither is an acceptable join substitute under this review.

**Outstanding requirements:** Supply the authoritative identifier specification, domain-owner confirmation of the referent and namespace, revision/project/plant uniqueness policy, and a data-backed explanation for the duplicate EngineeringBOM records before requesting approval.

## 3. Required semantic review questions

Each domain owner must provide an answer and a link to authoritative evidence:

- **Referent:** What exactly does `hasAssetIdentifier` identify (physical asset, functional location, equipment position, device, BOM record, or other)?
- **Authority and namespace:** Who issues the identifier? Is `https://aas.example.com/` a governed namespace? Are URI and literal forms normalized consistently?
- **Uniqueness scope:** Is uniqueness guaranteed within a project, plant, tenant, facility, or globally? What other keys are required to prevent accidental matches?
- **Lifecycle:** Are identifiers stable across design changes, replacements, versions, and retirement? Are they reused?
- **Cardinality:** Why are there two EngineeringBOM records per shared identifier? Can one DEXPI object represent multiple distinct assets or functions?
- **DEXPI alternatives:** Do all three DEXPI paths represent compatible asset identities, or must the mapping be split?
- **Exceptions:** What happens with missing, malformed, duplicated, or conflicting identifiers? Are there known false-positive equality matches?

## 4. Approval criteria (all required)

- [ ] Written domain-owner definitions for all four `hasAssetIdentifier` properties, with source references.
- [ ] Agreement on the **same real-world referent** and exact identity scope; document any necessary composite keys.
- [ ] Documented identifier authority, namespace, normalization, uniqueness, lifecycle, and reuse rules.
- [ ] Evidence-backed explanation of EngineeringBOM 2:1 cardinality and DEXPI path alternatives.
- [ ] Representative positive matches **and** adversarial / negative examples reviewed by domain owners.
- [ ] Named reviewer with authority across all four domains; written approval decision and date.
- [ ] Re-run automated tests and live GraphDB baseline; retain result and commit references.
- [ ] Confirm that the approved catalog plan, comparison, and domain list exactly match the reviewed scope.

## 5. Decision record — deliberately unfilled

| Field | Value |
| --- | --- |
| Decision | **Pending** |
| Authorized reviewer | **Not assigned** |
| Approval date | **Not provided** |
| Rationale | **Pending semantic evidence** |
| Evidence reference | `review/asset-identity-four-domain-001` (this document; not an approval) |
| Approved domains | **None** |
| Approved comparison | **None** |
| Limitations / exceptions | **To be documented** |

**No approval is implied by this document, the test suite, the GraphDB results, or the compiler's `--allow-candidate` flag.**

## 6. Controlled transition after a real approval

Only after the criteria above are satisfied and the authorized reviewer records a decision:

1. Record the signed-off reviewer, ISO date, rationale, evidence reference, domain list, and comparison in `semantic_approvals` within `semantic/ontology/dtwise/cross-domain-mappings.json`.
2. Change **only the reviewed mapping** status from `candidate_pending_semantic_approval` to `verified`. Do not promote the two- or three-domain mappings automatically.
3. Confirm the approval record is unique and matches the exact plan; governance must reject missing or mismatched records.
4. Run the regression suite and verify compilation **without** `--allow-candidate`, followed by the live GraphDB baseline.
5. Commit the approval evidence and catalog change together for auditability.

If the review discovers that identifier equality is insufficient, **do not approve** the existing plan. Instead, revise the mapping and its tests to require the additional grounded keys or domain-specific constraints, and repeat the review.
