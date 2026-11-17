# DTWise benchmark ID migration

The 53 existing benchmark questions were renumbered consecutively in manifest order. Questions, categories, and versions are unchanged. Historical reports retain their original IDs; use this table when comparing old reports to new runs.

| Old ID | New ID | Question |
|---|---|---|
| B01 | B01 | Get SignalName from OPCUAConnectivity. |
| B02 | B02 | Get LocalId of DEXPI InstrumentationFunctions. |
| B03 | B03 | List MeasuredVariable of DEXPI InstrumentationFunctions. |
| B04 | B04 | Show AssetName from AssetInventory. |
| B05 | B05 | Get ManufacturerName from ProductCatalog. |
| B06 | B06 | Show opcuaconnectivity SignalMapping signalName where assetIdentifier is https://aas.example.com/FI103. |
| B07 | B07 | Show dexpi InstrumentationFunction localId where localId is FI_103. |
| B08 | B08 | Show dexpi InstrumentationFunction measuredVariable where localId is FI_103. |
| B09 | B09 | Show opcuaconnectivity SignalMapping signalName where signalDirection is READ. |
| B10 | B10 | Show assetinventory Asset assetName where assetIdentifier is https://aas.example.com/FI103. |
| B13 | B11 | Get SignalName and OPCUANodeId from OPCUAConnectivity. |
| B14 | B12 | Show AssetIdentifier and AssetName for AssetInventory assets. |
| B15 | B13 | Get LocalId and AssetIdentifier of DEXPI InstrumentationFunctions. |
| B16 | B14 | Count SignalMappings in OPCUAConnectivity. |
| B17 | B15 | Count SignalMappings for each AssetIdentifier. |
| B18 | B16 | List AssetIdentifiers with more than three SignalMappings. |
| B19 | B17 | Get the first ten SignalNames in alphabetical order. |
| B20 | B18 | Which signal names are associated with asset https://aas.example.com/FI103? |
| B21 | B19 | For asset https://aas.example.com/FI103, list its signals. |
| B22 | B20 | Show me the signal names belonging to https://aas.example.com/FI103. |
| B23 | B21 | Get SignalName of the DEXPI InstrumentationFunction with LocalID FI-001. |
| B24 | B22 | Find SignalNames associated with DEXPI InstrumentationFunctions through AssetIdentifier. |
| B25 | B23 | Get OPCUANodeId for ECAD Devices matched by AssetIdentifier. |
| B26 | B24 | Join DEXPI, ECAD, OPCUAConnectivity and ProductCatalog through AssetInventory using AssetIdentifier and ProductIdentifier. |
| B27 | B25 | List AssetIdentifiers shared by DEXPI and OPCUAConnectivity. |
| B28 | B26 | Which DEXPI InstrumentationFunctions have an AssetIdentifier?  |
| B29 | B27 | Which DEXPI InstrumentationFunctions do not have an AssetIdentifier?  |
| B30 | B28 | List DEXPI Equipment without an AssetIdentifier. |
| B31 | B29 | List DEXPI Equipment and their LocalId, if available.  |
| B32 | B30 | Which DEXPI InstrumentationFunctions have no matching OPCUAConnectivity SignalMapping by AssetIdentifier?  |
| B38 | B31 | Which DEXPI entities have a LocalId containing TI_?  |
| B39 | B32 | Which OPC UA Connectivity entities have a SignalName starting with XMEAS?  |
| B40 | B33 | Which ProductCatalog entities have a ManufacturerName containing Endress?  |
| B41 | B34 | Which ECAD entities have a LocalId matching the regular expression ^PI-?  |
| B42 | B35 | Which AssetInventory entities have an AssetName containing reactor, ignoring case?  |
| B43 | B36 | Which DEXPI entities have both AssetIdentifier and LocalId?  |
| B44 | B37 | Which inventory assets have AssetName but no EquipmentTag?  |
| B45 | B38 | Which ECAD entities have an Address or LocalId?  |
| B46 | B39 | Which signal mappings have a SignalName and a MappingStatus?  |
| B47 | B40 | Which products have ManufacturerName but no SupplierName? |
| B48 | B41 | Count distinct SignalNames for OPCUA AssetIdentifier https://aas.example.com/FI103. |
| B49 | B42 | Show SignalNames ordered descending, limit 5. |
| B50 | B43 | List AssetNames whose AssetIdentifier is FI103 or FI104. |
| B51 | B44 | Get OPCUA SignalNames associated with DEXPI InstrumentationFunctions using AssetIdentifier. |
| B52 | B45 | Get OPCUA SignalNames for DEXPI InstrumentationFunction LocalId FI-001 using AssetIdentifier. |
| B53 | B46 | Find ECAD Device LocalIds associated with DEXPI InstrumentationFunctions via AssetIdentifier. |
| B54 | B47 | Show OPCUA SignalName and ECAD Device LocalId for shared AssetIdentifiers. |
| B55 | B48 | Find DEXPI InstrumentationFunctions and OPCUA SignalMappings matched through AssetInventory. |
| B56 | B49 | Get OPCUA SignalNames and ECAD Device LocalIds for DEXPI InstrumentationFunctions via AssetInventory. |
| B57 | B50 | Join DEXPI, ECAD, OPCUAConnectivity, AssetInventory and ProductCatalog on AssetIdentifier and ProductIdentifier; return SignalName and ManufacturerName. |
| B58 | B51 | For asset FI103, get OPCUA SignalName and ProductCatalog ManufacturerName through AssetInventory. |
| B59 | B52 | Count OPCUA SignalMappings per DEXPI InstrumentationFunction through AssetIdentifier. |
| B60 | B53 | List DEXPI InstrumentationFunctions with no matching OPCUA SignalMapping. |
