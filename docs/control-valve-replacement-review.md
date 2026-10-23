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


## Manufacturer-datasheet cross-check (2026-10-23)

SAMSON Type 3241-1/-7 manufacturer data sheet T 8016 EN confirms PN16–PN40 variants for DN15–DN150 in its safety-function series, water/steam temperature capability up to 350 °C subject to materials and pressure-temperature limits, and permissible differential pressure varying by actuator and valve configuration. See https://samson.de/document/t80160en.pdf . These are **family/variant** capabilities, not a guarantee for the existing catalog DN25/Kvs10/PN40 assembly.

| Signals | Service verification | Configuration status |
|---|---|---|
| XMV1–2 | D/E feeds; actual fluid state and sizing to verify | CANDIDATE_ONLY |
| XMV3–4 | A and A/C feed; gas compressibility and choking to check | CANDIDATE_ONLY |
| XMV5 | Compressor recycle; gas flow, pressure drop, anti-surge/recycle dynamics to check | HIGH_PRIORITY_UNVERIFIED |
| XMV6 | Purge gas; pressure drop and choking to check | CANDIDATE_ONLY |
| XMV7–8 | Separator liquid / stripper product; cavitation/flashing to check | CANDIDATE_ONLY |
| XMV9 | Steam; temperature, trim, choked flow and fail action to check | STEAM_CONFIG_UNVERIFIED |
| XMV10–11 | Cooling-water circuits; cavitation, differential pressure and valve response to check | CANDIDATE_ONLY |

**Result:** Family is defensible as a common simulation *candidate*. No per-signal valve sizing, Cv/Kvs, actuator sizing, fail-safe configuration, or configured assembly approval can be established from TEP nominal process values alone. The present ProductCatalog SAMSON_3241_7 entry remains a specific assembly; proposed references must not be interpreted as its approval for all eleven signals. ECLASS IRDI still requires authoritative validation.

The reference TEP manipulated-variable definitions are documented at https://github.com/PSE-Research/Tennessee-Eastman-profBraatz/blob/master/README.md .
