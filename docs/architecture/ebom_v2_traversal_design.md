# DTWiSE EBOM V2 — traversal-first design proposal

Status: **PROPOSED / NOT IMPLEMENTED**. Baseline V1 files and GraphDB data remain unchanged.

## Purpose
Use a Teamcenter-inspired distinction between engineering item identity, revision, and BOM occurrence, without copying proprietary Teamcenter schema. Keep process-plant context and functional engineering relationships separate from physical/product composition. Connect to DEXPI, ECAD, Asset Inventory, Product Catalog, OPC UA, and existing VTKG through typed, evidence-bearing links.

## Verified V1 inputs
- `semantic/templates/engineering_bom_template.json`: AAS Submodel with `Assemblies/Assembly` and `BOMItems/BOMItem` collections.
- `semantic/instances/tep/tep_engineering_bom_instance.json`: 22 assemblies, 79 BOM items (previous dataset inventory); `ASM-REACTOR` described as “Reactor Assembly — R-001”; `EBOM-0001` equipment `R-001` under `ASM-REACTOR`.
- `semantic/ontology/engineeringbom-template.ttl`: generated SHACL; `hasParentItemId` and `hasFunctionalAssemblyReference` are literal/datatype properties, not traversable object edges.
- Five DEXPI instrumentation function BOM records (`FI_106`, `TI_101`, `TI_104`, `LI_101`, `PI_101`) have `FunctionalAssemblyReference=ASM-REACTOR` and unverified physical membership. Do **not** convert these to structural BOM occurrences.

## Logical V2 entities
| Entity | Identity / semantics | Source or migration policy |
|---|---|---|
| PlantContext | Plant, unit, system, functional location; not a BOM component | Derive only from evidenced source groupings |
| EngineeringItem | Stable engineering part/equipment identity | Map only when an actual item identity is supported; do not conflate source BOM row with master item |
| ItemRevision | Revision-specific definition and lifecycle state | Preserve `UNSPECIFIED` as unknown; never fabricate a release revision |
| EngineeringAssembly | Assembly-capable EngineeringItem / context, not an unrelated second master | Classify existing assembly rows individually as product assembly vs plant context |
| BOMOccurrence | Use of a child item/revision under parent assembly/revision, with position, quantity, unit, effectivity | Materialize only for supported composition; preserve V1 parent evidence and provisional status |
| FunctionalAssociation | Typed association between engineering function/BOM source record and plant system/assembly | Materialize independently of physical membership |
| ExternalReference | Domain-specific target identity, identifier type, match basis, verification | Identifier equality is candidate association unless verified |
| EvidenceRecord | Source record, field, basis, status, lifecycle validity | Link to each derived assertion |

## Traversal vocabulary (proposed namespace `https://example.org/dtwise/core/`)
- `hasPlantContext`: engineering object → PlantContext.
- `hasBOMOccurrence`: parent ItemRevision → BOMOccurrence.
- `occurrenceOf`: BOMOccurrence → child ItemRevision.
- `functionalAssociationTarget`: FunctionalAssociation → PlantContext or EngineeringAssembly.
- `functionalAssociationSource`: FunctionalAssociation → source engineering record/function.
- `referencesExternalObject`: engineering record → external reference resource.
- `supportedByEvidence`: relationship resource → EvidenceRecord.
- `resolvedFromSourceId`: object → original literal identifier (preserve original value).
All object edges are additive **derived assertions**; retain V1 literals and source record IDs for traceability.

## Required graph paths
1. `R-001` → evidenced reactor equipment record `EBOM-0001` → its recorded assembly context `ASM-REACTOR` → functional associations → five DEXPI instrumentation function records (by asset identifier, with explicit match-basis evidence).
2. Assembly revision → BOM occurrence → child revision, **only** for verified or explicitly qualified structural relationships.
3. Engineering tag/function → external reference → Asset Inventory / Product Catalog / ECAD / OPC UA; never assume a link exists merely because a domain is available.
4. Operational signal → existing VTKG, if the source mappings support it; VTKG is not rebuilt by EBOM V2.

## Q1-B regression oracle
Reference query against current GraphDB returns precisely `FI_106`, `LI_101`, `PI_101`, `TI_101`, `TI_104` as functionally associated with `ASM-REACTOR`. This is **not** evidence of physical membership.
V2 must preserve these five answers and the association basis, while grounding the user-mentioned `R-001` through a source-supported mapping rather than hardcoded benchmark aliases.

## Validation gates
1. Inventory V1 assembly kinds, parent references, item types, revisions, quantity semantics, and source provenance. Classify each parent link as structural, contextual, or unresolved.
2. Define URI minting and stable identity rules, no collision between source records and master engineering items.
3. Require resolvable endpoints for object links; detect dangling references and structural cycles.
4. Require provenance and explicit verification/uncertainty status for every materialized derived relationship.
5. Assert functional associations do not imply BOM occurrence, installed-asset equivalence, or physical containment.
6. Preserve V1 counts, values and legacy query results in a separate baseline graph.
7. Validate generated RDF/SHACL in GraphDB and compare Q1-B and Q1–Q7 benchmark outputs before updating the generic planner.

## Implementation stages
**A. Audit:** source inventory and relationship classification, no data edits.
**B. Semantic overlay:** separate V2 RDF/SHACL named graph with derived typed edges and evidence. Prefer this before changing AAS templates.
**C. AAS V2 template:** introduce collections only where the AAS authoring/export workflow requires them; maintain V1 compatibility.
**D. Translator:** add grounded entity resolution and deterministic typed-path traversal, independent of benchmark-specific IDs.

## Non-goals
No claim of Teamcenter/COMOS software integration, no proprietary schema reproduction, no invented equipment/component breakdown, no automatic asset equivalence, no replacement of the existing VTKG.
