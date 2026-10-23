# TEP liquid-pump duty and product-family review (2026-10-23)

## Inventory interpretation

The current AssetInventory contains illustrative motor records M-1301 (`Stripper Pump Motor`), M-1401 (`Compressor Pump Motor`) and M-1501 (`Product Pump Motor`), all with unresolved `Rittal_3244100` ProductReferences. These are **not verified hydraulic pump assets**, and PLC outputs Q10.13–Q10.15 are illustrative, not independently verified Tennessee Eastman benchmark manipulated variables. M-1401 belongs to the **gas compressor drive** discussion and must not be assigned a liquid pump.

| Candidate duty | Relevant TEP measurement | Nominal measurement | Assessment |
|---|---|---|---|
| Separator liquid to stripper (possible transfer pump) | XMEAS14 separator underflow | 25.160 m³/h | Flow evidence only; pump presence, suction/discharge boundaries and head unverified |
| Stripper product liquid (possible product pump) | XMEAS17 stripper underflow | 22.949 m³/h | Flow evidence only; pump presence, suction/discharge boundaries and head unverified |
| Gas compressor drive | XMEAS20 compressor work | 230? **Do not infer pump power:** XMEAS20 is compressor work in kW | Not a liquid pump |

**Caution:** Vessel pressures around 26–31 bar(g) are nominal vessel measurements, not verified pump casing pressures, suction/discharge differential pressures or design pressure ratings. A line may be driven by vessel pressure without a pump. Do not infer a pump from the existence of liquid flow or an illustrative motor tag.

## Manufacturer screening

KSB **Etanorm** is an example industrial end-suction centrifugal pump family. The OEM lists maximum flow up to 2321 m³/h (60 Hz), maximum head 160 m and **maximum allowable working pressure 16 bar**, configuration-dependent. The 23–25 m³/h TEP nominal flow values fall within the family's broad flow envelope, **but that is not proof of compatibility**. If these pumps operate in the nominal 26–31 bar(g) vessel-pressure environment, a 16 bar working-pressure configuration is unsuitable. **Do not add Etanorm as a selected ProductCatalog candidate** without verified local pressure boundaries and a compliant higher-pressure pump family/configuration.

OEM: https://www.ksb.com/en-us/lc/products/pump/dry-installed-pump/etanorm-etanorm-myflow-etanorm-pro/e04b

## Sizing evidence gaps

For each potential liquid pump collect: verified P&ID and pump existence, suction/discharge pressure at normal/min/max conditions, static elevation, frictional losses, fluid density/viscosity/vapor pressure/composition and temperature, min/normal/max flow, NPSHa/NPSHr, casing design pressure and temperature, seals/materials, motor efficiency and duty. Hydraulic head is approximately `H = Δp/(rho*g) + Δz + Δ(v²)/(2*g) + losses` for a defined boundary; no numeric head or shaft power can be calculated from the benchmark measurements alone.

## Decision

- M-1301 and M-1501: **ILLUSTRATIVE_MOTOR / LIQUID_PUMP_DUTY_UNVERIFIED**; centrifugal-pump concept is provisional only.
- M-1401: **COMPRESSOR_DRIVE_NOT_LIQUID_PUMP**.
- No new pump product or ECLASS IRDI is added to ProductCatalog in this review. No AssetInventory ProductReferences are changed.
- Next: verify physical pump existence and pressure boundaries, then select a pressure-rated industrial process pump and run vendor curve/NPSH checks. Preserve provenance and avoid implying installed status.


## Benchmark topology verification (2026-10-23)

**Verified against a source-derived flowsheet:** The original TEP model's internal streams are explicitly enumerated in the `teprob.f` reconstruction at https://kitchingroup.cheme.cmu.edu/tep-rust/process/plant.html . It identifies FTM(11) as separator liquid underflow to stripper and FTM(13) as product; the five major units are reactor, condenser, separator, stripper and gas recycle compressor. The model's fifty state variables comprise vessel inventories/energies, cooling-water temperatures and 12 valve positions, **not pump-speed or pump-head states**. The benchmark therefore does **not establish a separately modeled separator-transfer pump or product pump**.

**Pressure boundary review:** XMEAS13 is separator vessel pressure, while XMEAS16 is labeled stripper pressure in the benchmark but the source-derived audit identifies it as **mixing-zone pressure** rather than an independent stripper vapour-space pressure. Consequently subtracting XMEAS16 from XMEAS13 to infer a transfer-pump differential pressure would be invalid. Neither stream FTM(11) nor FTM(13) has verified pump suction/discharge pressure taps. Do not use nominal vessel pressures to assert a pump head, pressure class or NPSH.

**Disposition:**
- `TEP_M_1301`: illustrative motor, **NO_BENCHMARK_PUMP_EVIDENCE**; keep as optional extended-plant concept only, not a validated physical pump.
- `TEP_M_1501`: illustrative motor, **NO_BENCHMARK_PUMP_EVIDENCE**; same restriction.
- `TEP_M_1401`: compressor drive concept, **NOT_A_LIQUID_PUMP**.
- No defensible high-pressure pump manufacturer/model can be selected for the benchmark on these data. An optional *augmented physical plant* requires a new P&ID, stream pressure boundary conditions, pump hydraulic model and design pressure basis before product-family screening.
- **No catalog or inventory mutations** are appropriate until the user elects to model additional physical pumps beyond the original TEP benchmark.

Sources: https://kitchingroup.cheme.cmu.edu/tep-rust/process/plant.html ; https://kitchingroup.cheme.cmu.edu/tep-rust/process/instrumentation.html ; Downs and Vogel (1993), original benchmark.
