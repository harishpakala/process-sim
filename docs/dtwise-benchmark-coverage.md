# DTWise benchmark coverage inventory

Canonical manifest: `frontend/public/dtwise-benchmark-manifest.json` from `feature/dtwise-query-operations` (blob `ac6041c783558bbcad58185586aff389da0ec7c8`).

This manifest has 53 entries (B01–B60, excluding B11, B12, B33–B37). The presence of a case here is **not** a pass result.

## Capability inventory

| Capability | Manifest IDs |
|---|---|
| Basic SHACL-grounded projection | B01–B05 |
| Literal equality filters | B06–B10 |
| Multiple projections | B13–B15 |
| Count, grouped count, HAVING, sorting/limit | B16–B19 |
| Paraphrase/coreference and entity grounding | B20–B22 |
| Verified cross-domain joins | B23–B27 |
| Property existence, absence and optional projection, anti-join | B28–B32 |
| Substring, prefix, regex and case folding | B38–B42 |
| Boolean property existence (AND/OR/NOT) | B43–B47 |
| Distinct count, ordering, disjunction | B48–B50 |
| Multi-domain/multi-hop relationships, optional path, anti-join, grouped count | B51–B60 |

## Acceptance gates

1. Every manifest ID has a planned semantic intent (entities, join path, projection, operator, filters, grouping, sorting).
2. LLM-first selection succeeds **without** a deterministic NL fallback, or reports a precise unsupported/evidence error.
3. Every compiled SPARQL query is checked for correct joins and modifiers, not merely successful generation.
4. GraphDB execution and returned answer semantics are checked separately. Empty results do not establish query correctness.
5. Results must distinguish: planning success, semantic validation, compilation, execution and answer correctness. Do not mark cases as passing without observed evidence.

## Authoritative question list

| ID | Category | Exact manifest question |
|---|---|---|
| B01 | basic | Get SignalName from OPCUAConnectivity. |
| B02 | basic | Get LocalId of DEXPI InstrumentationFunctions. |
| B03 | basic | List MeasuredVariable of DEXPI InstrumentationFunctions. |
| B04 | basic | Show AssetName from AssetInventory. |
| B05 | basic | Get ManufacturerName from ProductCatalog. |
| B06 | filters | Show opcuaconnectivity SignalMapping signalName where assetIdentifier is https://aas.example.com/FI103. |
| B07 | filters | Show dexpi InstrumentationFunction localId where localId is FI_103. |
| B08 | filters | Show dexpi InstrumentationFunction measuredVariable where localId is FI_103. |
| B09 | filters | Show opcuaconnectivity SignalMapping signalName where signalDirection is READ. |
| B10 | filters | Show assetinventory Asset assetName where assetIdentifier is https://aas.example.com/FI103. |
| B13 | multiple_projections | Get SignalName and OPCUANodeId from OPCUAConnectivity. |
| B14 | multiple_projections | Show AssetIdentifier and AssetName for AssetInventory assets. |
| B15 | multiple_projections | Get LocalId and AssetIdentifier of DEXPI InstrumentationFunctions. |
| B16 | aggregation | Count SignalMappings in OPCUAConnectivity. |
| B17 | aggregation | Count SignalMappings for each AssetIdentifier in OPCUAConnectivity. |
| B18 | aggregation | List AssetIdentifiers with more than three SignalMappings in OPCUAConnectivity. |
| B19 | aggregation | Get the first ten SignalNames in alphabetical order from OPCUAConnectivity. |
| B20 | language_variation | Which SignalNames in OPCUAConnectivity are associated with AssetIdentifier https://aas.example.com/FI103? |
| B21 | language_variation | For asset https://aas.example.com/FI103, list its signals. |
| B22 | language_variation | Show me the signal names belonging to https://aas.example.com/FI103. |
| B23 | Cross-domain | Get SignalName from OPCUAConnectivity for the DEXPI InstrumentationFunction with LocalID FI-001, matched through AssetIdentifier. |
| B24 | Cross-domain | Find SignalName from OPCUAConnectivity associated with DEXPI InstrumentationFunctions through AssetIdentifier. |
| B25 | Cross-domain | Get OPCUANodeId from OPCUAConnectivity for ECAD Devices matched through AssetIdentifier. |
| B26 | Cross-domain | Join DEXPI, ECAD, OPCUAConnectivity and ProductCatalog through AssetInventory using AssetIdentifier and ProductIdentifier. |
| B27 | Cross-domain | List AssetIdentifiers shared by DEXPI and OPCUAConnectivity. |
| B28 | Single Domain | Which DEXPI InstrumentationFunctions have an AssetIdentifier? |
| B29 | Single Domain | Which DEXPI InstrumentationFunctions do not have an AssetIdentifier? |
| B30 | Single Domain | List DEXPI Equipment without an AssetIdentifier. |
| B31 | Single Domain | List DEXPI Equipment and their LocalId, if available. |
| B32 | Cross-domain | Which DEXPI InstrumentationFunctions have no matching OPCUAConnectivity SignalMapping by AssetIdentifier? |
| B38 | String filtering | Which DEXPI entities have a LocalId containing TI_? |
| B39 | String filtering | Which OPC UA Connectivity entities have a SignalName starting with XMEAS? |
| B40 | String filtering | Which ProductCatalog entities have a ManufacturerName containing Endress? |
| B41 | String filtering | Which ECAD entities have a LocalId matching the regular expression ^PI-? |
| B42 | String filtering | Which AssetInventory entities have an AssetName containing reactor, ignoring case? |
| B43 | Boolean | Which DEXPI entities have both AssetIdentifier and LocalId? |
| B44 | Boolean | Which inventory assets have AssetName but no EquipmentTag? |
| B45 | Boolean | Which ECAD entities have an Address or LocalId? |
| B46 | Boolean | Which signal mappings have a SignalName and a MappingStatus? |
| B47 | Boolean | Which products have ManufacturerName but no SupplierName? |
| B48 | compound_filters | Count distinct SignalNames for OPCUA AssetIdentifier https://aas.example.com/FI103. |
| B49 | compound_filters | Show SignalNames ordered descending, limit 5. |
| B50 | compound_filters | List AssetNames whose AssetIdentifier is FI103 or FI104. |
| B51 | multi_domain_multi_hop | Get OPCUA SignalNames associated with DEXPI InstrumentationFunctions using AssetIdentifier. |
| B52 | multi_domain_multi_hop | Get OPCUA SignalNames for DEXPI InstrumentationFunction LocalId FI-001 using AssetIdentifier. |
| B53 | multi_domain_multi_hop | Find ECAD Device LocalIds associated with DEXPI InstrumentationFunctions via AssetIdentifier. |
| B54 | multi_domain_multi_hop | Show OPCUA SignalName and ECAD Device LocalId for shared AssetIdentifiers. |
| B55 | multi_domain_multi_hop | Find DEXPI InstrumentationFunctions and OPCUA SignalMappings matched through AssetInventory. |
| B56 | multi_domain_multi_hop | Get OPCUA SignalNames and ECAD Device LocalIds for DEXPI InstrumentationFunctions via AssetInventory. |
| B57 | multi_domain_multi_hop | Join DEXPI, ECAD, OPCUAConnectivity, AssetInventory and ProductCatalog on AssetIdentifier and ProductIdentifier; return SignalName and ManufacturerName. |
| B58 | multi_domain_multi_hop | For asset FI103, get OPCUA SignalName and ProductCatalog ManufacturerName through AssetInventory. |
| B59 | multi_domain_multi_hop | Count OPCUA SignalMappings per DEXPI InstrumentationFunction through AssetIdentifier. |
| B60 | multi_domain_multi_hop | List DEXPI InstrumentationFunctions with no matching OPCUA SignalMapping. |
