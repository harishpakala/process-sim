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


## Valve-by-valve sizing evidence audit (2026-10-23)

**Method:** Cross-reference AssetInventory XMV1–XMV11 with the original TEP nominal measurement definitions and the SAMSON IEC 60534 sizing requirements. A nominal measurement from a nearby stream is *not* assumed to equal valve-throughput under all conditions. No pressure taps immediately upstream and downstream of each valve, valve-specific fluid state, piping DN, or fluid property package were verified in the available AAS records. Consequently **zero of eleven valves can be assigned a defensible numerical Kv/Cv**. This is a completed evidence audit, not a completed engineering sizing calculation.

| XMV | Duty | Potential TEP measurement to examine (nominal) | Required additional inputs | Numerical Kv/Cv |
|---|---|---|---|---|
| 1 | D feed | XMEAS2: 3664.0 kg/h | Valve inlet/outlet pressure, density, phase, piping size, min/max flow | BLOCKED |
| 2 | E feed | XMEAS3: 4509.3 kg/h | Valve inlet/outlet pressure, density, phase, piping size, min/max flow | BLOCKED |
| 3 | A feed | XMEAS1: 0.25052 kscmh | Valve inlet/outlet absolute pressures, gas mixture MW, T, Z, reference state, min/max flow | BLOCKED |
| 4 | A/C feed | XMEAS4: 9.3477 kscmh | Valve inlet/outlet absolute pressures, gas mixture MW, T, Z, reference state, min/max flow | BLOCKED |
| 5 | Compressor recycle | XMEAS5 recycle flow: 26.902 kscmh **not established as the flow through XMV5** | Actual recycle-bypass flow, compressor operating map, pressures, gas state, dynamic anti-surge constraints | BLOCKED — HIGH PRIORITY |
| 6 | Purge | XMEAS10: 0.33712 kscmh | Valve inlet/outlet absolute pressures, gas MW, T, Z, reference state, min/max flow | BLOCKED |
| 7 | Separator liquid to stripper | XMEAS14: 25.160 m³/h | Valve inlet/outlet pressure, liquid density, vapor pressure, min/max flow | BLOCKED |
| 8 | Stripper product | XMEAS17: 22.949 m³/h | Valve inlet/outlet pressure, liquid density, vapor pressure, min/max flow | BLOCKED |
| 9 | Stripper steam | XMEAS19: 230.31 kg/h | Steam supply pressure, downstream pressure, temperature, dryness/enthalpy, steam tables, min/max flow | BLOCKED — HIGH PRIORITY |
| 10 | Reactor cooling-water valve | No directly validated cooling-water flow measurement | Actual water flow, valve Δp, density, vapor pressure, min/max flow | BLOCKED |
| 11 | Condenser cooling-water valve | No directly validated cooling-water flow measurement | Actual water flow, valve Δp, density, vapor pressure, min/max flow | BLOCKED |

**Crucial caution:** XMEAS5 is process recycle flow, whereas XMV5 manipulates compressor recycle/bypass; direct equivalence is unverified. Reactor/separator pressure measurements are vessel pressures, not valve upstream/downstream pressure pairs. TEP XMV commands are not flow coefficients.

### Sizing method once evidence exists

- **Single-phase liquid, simplified non-choked case:** `Kv = Q_m3h × sqrt((rho_kgm3/1000)/deltaP_bar)`. Example **illustration only**, not a TEP calculation: at 25.160 m³/h, rho=1000 kg/m³ and assumed Δp=1 bar, Kv=25.160. Different actual Δp or density changes the result.
- **Gas/steam:** use IEC 60534-2-1 compressible-fluid equations with absolute pressures, inlet temperature, gas properties or steam specific volume, expansion factor and choking checks. Do not substitute standard-volume flows without a verified standard reference state.
- Select Kvs, DN, trim, actuator thrust, fail position and permissible differential pressure only *after* Kv calculations and operating-envelope checks. The existing catalog Kvs10 assembly must not be approved by inference.

References: Downs & Vogel (1993), https://users.abo.fi/khaggblo/RS/Downs.pdf ; SAMSON control valve specification sheet, https://www.samson.de/document/k00200en.pdf ; SAMSON valve selection/sizing, https://www.samsongroup.com/document/t80430en.pdf ; IEC 60534-2-1 compressible-fluid sizing overview, https://www.iteh.eu/catalog/standards/sist/a3615b03-2b10-4d43-a04a-8af5c430bb33/sist-en-60534-2-1-2011 .

**Decision:** Maintain eleven distinct valve assets and SAMSON Type 3241 as an unverified family candidate; no ProductReference or configured sizing approval changes warranted.
