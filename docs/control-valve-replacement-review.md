# TEP control valve replacement review

Status: **simulation-scope candidate mapping only**, not sizing approval or verified installation.

## Catalog integrity

Eleven AssetInventory manipulated variables (XMV1–XMV11) currently refer to `https://example.org/product-types/Siemens_S55264_V193`, which is **not present** in the current ProductCatalog. The existing ProductCatalog includes `SAMSON_3241_7` (Type 3241-7 pneumatic globe valve assembly), specified as DN25, Kvs 10 m³/h, PN40 with Type 3277 actuator and Type 3730-1 positioner. That **particular configured assembly has not been qualified** for all duties. Preserve the Siemens references as original mappings.

## Eleven valve duties

| Signal | Existing asset description | Group | Proposed family | Status |
|---|---|---|---|---|
| XMV1 | Feed D control | Feed control | SAMSON Type 3241 | Candidate |
| XMV2 | Feed E control | Feed control | SAMSON Type 3241 | Candidate |
| XMV3 | Feed A control | Feed control | SAMSON Type 3241 | Candidate |
| XMV4 | Feed A and C control | Feed control | SAMSON Type 3241 | Candidate |
| XMV5 | Recycle flow control | Gas recycle/purge | SAMSON Type 3241 | Candidate |
| XMV6 | Purge flow control | Gas recycle/purge | SAMSON Type 3241 | Candidate |
| XMV7 | Stripper inlet control | Liquid/product control | SAMSON Type 3241 | Candidate |
| XMV8 | Product outlet control | Liquid/product control | SAMSON Type 3241 | Candidate |
| XMV9 | Stripper steam feed control | Stripper steam feed | SAMSON Type 3241 | Candidate |
| XMV10 | Reactor cooling-water return | Cooling water | SAMSON Type 3241 | Candidate |
| XMV11 | Condenser outlet | Cooling water | SAMSON Type 3241 | Candidate |

XMV12 is the reactor agitator/motor control and **is not a valve**.

## Engineering limitations

1. Valve command percentages in the benchmark are **not** measured flow rates or valve Cv/Kvs. Do not infer a required Kvs from command percentages.
2. Size each duty using the applicable medium, normal/fault flow envelope, upstream/downstream pressures, pressure drop, fluid properties, cavitation/flashing/choked-flow checks, and required rangeability.
3. Confirm actuator action, fail-safe position, valve characteristic, response time, positioner control, and steam-specific/cooling-water-specific duty.
4. Verify configured valve pressure class, size and trim before assigning an orderable assembly. PN40 is a class of the current catalog assembly, not a blanket suitability guarantee.
5. Resolve ECLASS class IRDI `0173-1#01-AAD651#023` and relevant property IRDIs against an authoritative release before treating them as verified.
6. Keep OPC UA bindings and installation status provisional. Existing Siemens references are preserved; `ProposedReplacementProductReference` indicates only an unverified family candidate.

## Manufacturer evidence

- SAMSON Type 3241 globe valve family: https://www.samsongroup.com/en/products-applications/products/control-valves/globe-valves/type-3241/
- Existing ProductCatalog record `SAMSON_3241_7` contains the configured assembly's values; these must not be propagated as specifications of all candidate valves.
