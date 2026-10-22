# AssetInventory semantic classification policy

The AssetInventory JSON is in `examples/aas/asset_inventory_instance.json`.

## Distinguish equipment from simulated signals

- The five `SimulatedEquipment` records (reactor, condenser, separator, compressor, stripper) carry the same **working ECLASS class IRDIs** as their linked ProductCatalog candidate families. The project's ECLASS mappings have **not been independently checked against an official ECLASS release**.
- The 41 `LogicalMeasurement` records are simulation measurements, not evidence of physical installed sensors. They carry the **project-defined** semantic concept `https://example.org/tep/ontology/asset-inventory#LogicalMeasurement`.
- The 11 `LogicalManipulatedVariable` records are simulated control inputs, even when their names mention valves. They are **not** certified physical valves. They carry `https://example.org/tep/ontology/asset-inventory#LogicalManipulatedVariable`.
- `TEP_XMV12` is a logical motor control signal; its semantic concept is `https://example.org/tep/ontology/asset-inventory#LogicalMotorControl`.
- Three separately modeled `IllustrativeMotor` entries and one `IllustrativeControlValve` entry have project-defined semantic concepts `#IllustrativeMotor` and `#IllustrativeControlValve`. They are **not** identified manufacturer equipment; a physical ECLASS class must be verified for each before replacing the local concept.

## Semantics and limitations

An asset entry's `semanticId` expresses its *classification*, not the unique identity of that record. The `AssetId` property remains the instance identifier. `EquipmentTag` is the engineering tag. `CandidateProductReference` is only a proposed product-family link; it does not mean selected, purchased, approved or installed equipment.

The `example.org` concept IRIs above are **local working identifiers**, not registered or dereferenceable published ontology terms. They must be replaced or defined in a published, versioned vocabulary before external RDF/GraphDB interoperability is claimed. No ECLASS IRDI is invented for logical signals.

## Follow-up validation gates

1. Verify all ECLASS class/IRDI pairs against the intended official ECLASS release and licensing conditions.
2. Establish and publish an authoritative project vocabulary for logical and illustrative entities, or map them to suitable existing standards.
3. Validate AAS JSON against the target metamodel and check UI display of `semanticId` for each collection.
4. Add physical device classifications only when the engineering model actually establishes the device type; avoid conflating measurements/control commands with sensors/valves.
5. Verify DEXPI equipment cross-references, candidate link integrity, and RDF lifting before GraphDB publication.
