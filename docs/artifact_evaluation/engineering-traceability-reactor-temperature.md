# TEP NEXUS engineering traceability audit: reactor temperature

**Scope:** Static, source-level audit of the six AAS JSON instance models and the committed discovery/coverage snapshots. This is **not** a live GraphDB traversal or an independently verified physical installation. Audited branch: `feature/deterministic-nexus-baseline-20261110` (2026-11-10).

## 1. Evidence-backed candidate path

| Layer | Source evidence | Interpretation and limitation |
| --- | --- | --- |
| DEXPI instrumentation function | [DEXPI instance](../../examples/aas/tep_dexpi_instance.json): `ReactorTemperature`, `LocalId=TI_101`, `SourceAssetIdentifier=https://aas.example.com/TI_101`, `AssetIdentifier=https://aas.example.com/TI101` | Source engineering function; shared identifier is modeled, not physically verified |
| ECAD device | [ECAD instance](../../examples/aas/tep_ecad_instance.json): `TI_1101`, `LocalId=TI-1101`, `SourceAssetIdentifier=https://aas.example.com/TI-1101`, `AssetIdentifier=https://aas.example.com/TI101`, `DeviceType=Temperature` | DEXPI and ECAD objects share the **same modeled AssetIdentifier**, despite different local IDs. The ECAD entry lists `Manufacturer=SMC` and `PartNumber=PSH-L2-01-W`; these are source attributes, not independently validated installation evidence |
| AAS AssetInventory | [AssetInventory instance](../../examples/aas/asset_inventory_instance.json): `TEP_XMEAS9`, `AssetIdentifier=https://aas.example.com/TI101`, `EquipmentTag=TI-1101`, `AssetType=LogicalMeasurement`, `OperationalReference=XMEAS9`, `ModelingStatus=EngineeringDefined` | Explicit shared identifier connects the model records; asset is explicitly a **logical measurement**, not a verified installed transmitter |
| Engineering BOM (DEXPI source) | [EBOM instance](../../examples/aas/tep_engineering_bom_instance.json): `EBOM-0016`, `EngineeringReference=https://aas.example.com/TI101`, `EngineeringLocalId=TI_101`, `ItemDescription=ReactorTemperature` | BOM **engineering-object record**, not procurement evidence. `AssetReference` and `CandidateProductReference` are empty; `ValidationStatus=UNRESOLVED_ASSET_REFERENCE` |
| Engineering BOM (ECAD source) | [EBOM instance](../../examples/aas/tep_engineering_bom_instance.json): `EBOM-0050`, `EngineeringReference=https://aas.example.com/TI-1101`, `EngineeringLocalId=TI-1101`, `ItemDescription=TI_1101` | Separate engineering-object BOM record. `EquivalenceStatus=NOT_ASSESSED_ACROSS_DOMAINS`; **do not** describe these two BOM items as a reconciled physical component |
| Product catalog candidate | [ProductCatalog instance](../../examples/aas/product_catalog_instance.json): `IFM_TA1101`, `ProductIdentifier=https://example.org/product-types/IFM_TA1101`, `SelectionStatus=SIMULATION_SCOPE_APPROVED_FAMILY` | AssetInventory refers to this **candidate product family**. This does **not** prove that a specific IFM part is installed. The ECAD source lists a different SMC part; the discrepancy requires explicit treatment |
| Engineering function → signal | [OPC UA Connectivity instance](../../examples/aas/tep_opcua_connectivity_instance.json): `ReactorTemperature`, `EngineeringFunctionId=TI_101`, `EngineeringFunctionReference=https://aas.example.com/TI101`, `SignalName=XMEAS9`, `OPCUANodeId=nsu=urn:process-sim:opcua;s=TEP.Measurements.XMEAS9` | Explicit provisional mapping; `MappingStatus=PROVISIONAL_ENGINEERING_MATCH`, `MappingBasis=TEP benchmark signal meaning; live OPC UA binding not verified` |
| Mapping-discovery snapshot | [Mapping discovery](../../reports/tep_nexus_mapping_discovery.json): `TI_101` has a unique provisional `XMEAS9` mapping | Snapshot evidence, **not** independent mapping validation |
| Historian coverage snapshot | [Temporal coverage](../../reports/tep_nexus_temporal_coverage.json): `TI_101 → XMEAS9`, `sample_count=1201`, `latest_simulation_seconds≈3514.0` | Indicates recorded coverage for run `10cfb1d1-2984-4932-8207-dc430ed60c2b`; it does **not** archive individual observation values or establish that the three-arm experiment used this same run |

### Identifier reconciliation

`TI_101` (DEXPI engineering local ID), `TI-1101` (ECAD device local ID and AssetInventory equipment tag), and `TI_1101` (ECAD collection idShort) **are not identical strings**. Their common `AssetIdentifier=https://aas.example.com/TI101` provides an explicit **model-level correlation**. The correlation is stronger than a naming guess but is not a physically validated identity assertion. The separate source identifiers must remain visible in provenance.

### Traceability interpretation

The static source files support a *modeled cross-domain path*:

```text
DEXPI ReactorTemperature [TI_101]
   └── AssetIdentifier https://aas.example.com/TI101
       ├── ECAD TI_1101 [LocalId TI-1101; same AssetIdentifier]
       ├── AssetInventory TEP_XMEAS9 [logical measurement; same AssetIdentifier]
       │   └── ProductCatalog IFM_TA1101 [simulation-scope candidate, not installed]
       └── EBOM-0016 [DEXPI engineering object; unresolved asset reference]
           EBOM-0050 [ECAD engineering object; equivalence not assessed]

OPC UA Connectivity: TI_101 → XMEAS9 [provisional]
Historian coverage: XMEAS9, 1,201 samples [historical run-scoped snapshot]
```

**Important:** This diagram is a *source-file reconciliation*, not a single executed RDF path query. In particular, the two EBOM records cannot be asserted as verified material or installed-device membership. The observed coverage snapshot alone does not provide actual sample timestamps/values for a reproducible plotted trace.

## 2. Cross-run provenance issue

The archived [three-arm result JSON](../../reports/tep_nexus_three_arm_experiment.json) reports run ID `077a3c31-44f4-4f3a-b06d-ad52b148fe10`. The committed [temporal coverage snapshot](../../reports/tep_nexus_temporal_coverage.json) reports a **different** run ID, `10cfb1d1-2984-4932-8207-dc430ed60c2b`. Therefore, do **not** claim that this coverage snapshot independently verifies the exact historian observations used in the three-arm latency experiment. A new run-specific coverage export and read-only observation query are needed for that stronger claim.

## 3. Reproduction checklist for the manuscript example

1. Confirm that the six JSON source instances are the versions lifted into the GraphDB repository used for the experiment. The root README's default lifting commands cover only DEXPI, ECAD, and ProductCatalog; the other domains require explicit loading/verification.
2. Run a read-only GraphDB query that returns the DEXPI/ECAD/AssetInventory/BOM/OPC UA source identifiers and their exact relationship predicates; save the query and result rows. Do not infer that JSON-level shared identifiers imply RDF links unless the lifting/mapping actually materializes them.
3. Select the **same** verified historian run as the experiment, then retrieve actual `XMEAS9` timestamps and values for a documented interval. Archive a sanitized result CSV and its query.
4. Reconcile the ECAD SMC source attributes with the AssetInventory IFM product-family candidate. Label unresolved selection/installation status rather than choosing one vendor as fact.
5. Only after steps 1–4, create the paper's one-row traceability table or figure and label each link as *source asserted*, *provisional mapping*, or *historian observed*.

## 4. Publication-safe preliminary statement

> In the illustrative reactor-temperature example, the DEXPI function `TI_101`, ECAD device `TI-1101`, and AssetInventory logical measurement `TEP_XMEAS9` share the modeled asset identifier `https://aas.example.com/TI101`. The OPC UA Connectivity model provisionally maps `TI_101` to `XMEAS9`, while a historical run-scoped coverage snapshot reports 1,201 samples for that signal. The engineering BOM contains separate DEXPI and ECAD engineering-object records with unresolved asset references, and the product catalog contains a simulation-scope candidate rather than an installed-device assertion. This demonstrates a traceable *model-level correspondence*, not verified physical component equivalence or independent historian-ground-truth validation.

**Do not describe this preliminary statement as a completed live end-to-end trace until the GraphDB traversal and matching historian observation rows have been archived.**
