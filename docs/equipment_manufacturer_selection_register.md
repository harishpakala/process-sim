# TEP NEXUS — manufacturer-backed equipment candidate register

Status: **research shortlist, not an approved equipment selection**. Updated 2026-10-21 with measured fault-free TEP operating-envelope screening.

The Tennessee Eastman Process (TEP) is a simulation benchmark, not a procurement design package. These seven entries are **manufacturer-backed product families or engineered offerings**, not confirmed installed products. ECLASS class/IRDI values are inherited from the project's README working classification register; **they have not been independently checked against the official ECLASS release**. No manufacturer part number, equipment rating, asset tag, or purchase claim is inferred.

| TEP equipment | ECLASS class | ECLASS IRDI | Manufacturer / candidate | Evidence and verified manufacturer-family facts | Selection status | Engineering information still required |
|---|---|---|---|---|---|---|
| Reactor | 36-02-01 | `0173-1#01-AAD319#012` | De Dietrich — BE glass-lined reactor family (**standard configuration screened out**) | [Official manufacturer page](https://www.dedietrich.com/en/equipment/process/reaction-agitation/glass-lined-reactors) confirms standard BE design pressure −1/+6 bar, below observed reactor pressure 27.05–27.13 bar(g); customized conditions require separate written manufacturer confirmation | **Standard BE: incompatible with observed pressure; customized BE: unverified** | Vessel volume, design/operating pressure, temperature, heat-transfer duty, reactants/material compatibility, agitator interface, official model datasheet |
| Condenser | 36-04 | `0173-1#01-AAD338#010` | Alfa Laval — Olmi process shell-and-tube exchangers | Manufacturer confirms fully customized process shell-and-tube exchangers for chemical/petrochemical applications; condensation suitability for the TEP duty is **not verified**. [Manufacturer source](https://www.alfalaval.com/en-GB/products/heat-transfer/tubular-heat-exchangers/process-shell-and-tube-heat-exchangers/) | **Verified offering; duty validation pending** | Heat duty, inlet/outlet temperatures, vapor composition, cooling utility, fouling, pressure drops, mechanical design |
| Gas–liquid separator | 36-20-17-04 | `0173-1#01-AKL760#020` | Didion Vessel — Type DSL; compare Type DST if liquid loading is high | DSL is a real horizontal/downflow gas–liquid separator; manufacturer states 99% removal of droplets/debris >=10 µm under its published conditions. DST is offered for larger horizontal liquid loads. [DSL](https://didionvessel.com/gas-separators/gas-liquid-separators/) · [DST](https://didionvessel.com/gas-separators/steam-separators/) | **Verified offering; service validation pending** | Gas and liquid flow rates, droplet-size target, liquid fraction, orientation, pressure, temperature, materials, corrosion |
| Recycle gas compressor | 36-43 | `0173-1#01-AAD585#011` | Atlas Copco — GT-Series centrifugal compressor | Manufacturer confirms engineered-to-order, integrally geared centrifugal compressors, family capabilities up to 500,000 m³/h and 205 bar, not a selected unit's ratings. [Manufacturer source](https://www.atlascopco.com/gas-and-process/en/products/centrifugal-compressors/gt-series) | **Verified offering; service and ECLASS assignability pending** | Gas composition and molecular weight, suction/discharge conditions, actual volumetric flow, pressure ratio, compressor map, sealing, driver selection; confirm assignable ECLASS leaf |
| Stripper | 36-01-01 | `0173-1#01-AAD304#013` | **Sulzer — engineered stripping column / turnkey stripping unit** | Manufacturer explicitly offers column internals **and column shells**, engineering packages, and complete stripping units. This resolves the prior Koch-Glitsch internals-only gap. [Manufacturer source](https://www.sulzer.com/en/shared/products/stripping) | **Verified complete-equipment offering; process design pending** | Separation target, feed/stripping agent composition and flow, pressure, temperature, stages/packing, reboiler/condenser interfaces |
| Reactor agitator assembly | 36-09-08-01 | `0173-1#01-AKP267#021` | EKATO — HWL-N reactor agitator | Manufacturer lists family motor power 5–4,000 kW, shaft diameter 40–560 mm and vacuum–200 bar operating pressure. Family range is **not a TEP design point**. [Manufacturer source](https://www.ekato.com/products/agitators/reactor-agitators-ekato-hwl-n/) | **Verified offering; mechanical sizing pending** | Reactor geometry, viscosity, mixing and mass-transfer duty, shaft speed/torque, sealing, motor/gearbox scope |
| Separately modeled drive motors | 27-02-24 | `0173-1#01-AKE158#012` | ABB — AMZ synchronous motor family | ABB confirms AMZ synchronous motors, 1–65 MW and 1–15 kV for published families; the **minimum family rating may be inappropriate** for some TEP pumps/agitators. [Manufacturer source](https://new.abb.com/motors-generators/synchronous-motors/synchronous-motors/synchronous-dol-8-40-poles-motors/technical-data) | **Verified motor family; individual drives and synchronous assumption unverified** | Separate pump/compressor/agitator shaft power, speed, supply voltage, hazardous-area requirements, starting method; confirm each drive is actually synchronous |

## Decision rules

1. **Do not add these seven as selected commercial products yet.** Candidate status is not the same as TEP fit, engineering approval, or procurement.
2. For engineered-to-order equipment, use the documented manufacturer **product family / engineered offering**, and leave `ManufacturerPartNumber` absent unless an actual manufacturer identifier is published and verified.
3. Verify ECLASS class assignability and release/version separately; the README IRDIs are **working project mappings**.
4. Record **published family ranges** separately from **project design requirements** and **chosen configuration values**. Do not substitute one for another.
5. Keep the agitator assembly distinct from a separately modeled motor; avoid counting the same drive twice.
6. Link a candidate product to an AssetInventory installed asset only after the asset/product choice is explicitly approved; keep DEXPI equipment identity independent of the commercial product selection.

## Validation gates before ProductCatalog integration

- [x] Obtain official De Dietrich BE family page and identify standard −1/+6 bar design-pressure limitation; standard BE is excluded for the observed 27+ bar(g) reactor service. A custom high-pressure variant is not approved.
- [ ] Extract process requirements for each equipment item from the TEP model and mark unavailable inputs as explicit engineering assumptions.
- [ ] Verify condenser duty and separator phase-loading applicability.
- [ ] Confirm compressor type, process gas compatibility and ECLASS class assignability.
- [x] Identify a **complete stripping-column offering** (Sulzer).
- [ ] Confirm agitator and motor equipment boundaries and individual drive powers.
- [ ] Check ECLASS mappings against the project's selected official ECLASS release.
- [ ] Review/approve candidate selections before writing ProductCatalog AAS entries, linking assets, lifting RDF and publishing to GraphDB.

## Evidence policy

Links above are primary manufacturer sources. A manufacturer-family capability is evidence that an offering exists, **not evidence of suitability** for the benchmark. Candidate selections can change as design requirements become available.

## Simulation-backed operating-envelope screening (2026-10-21)

**Evidence:** user-provided `tep_operating_envelope.csv`, produced from the project's fault-free TEP recording and operating-envelope script. The analyzed window was the second hour of a two-hour simulation (`--steady-start 1`); all 20 reported signals contain **361 samples**. This document records measured summary values, **not** a complete time series, certified steady-state determination, mechanical design basis, fault envelope, or procurement approval. CSV source is an uploaded analysis artifact and is not committed to this repository.

| Equipment / measured signal | Mean | Observed minimum–maximum | Screening decision and open requirements |
|---|---:|---:|---|
| Reactor pressure XMEAS(7) | 2708.89 kPa(g) / 27.09 bar(g) | 2705.49–2713.34 kPa(g) / 27.05–27.13 bar(g) | **Exclude standard De Dietrich BE −1/+6 bar configuration.** Require independently certified reactor design pressure, corrosion compatibility, vessel volume and temperature margins. |
| Reactor temperature XMEAS(9) | 120.40 °C | 120.34–120.44 °C | Published BE standard temperature range −25/+200 °C includes this observation, but temperature compatibility does **not** override the pressure failure. |
| Reactor level XMEAS(8) | 74.91% | 73.35–76.22% | Percent level does not determine vessel gross volume or allowable fill without geometry and model calibration. |
| Separator pressure XMEAS(13) | 2638.03 kPa(g) / 26.38 bar(g) | 2634.26–2643.10 kPa(g) / 26.34–26.43 bar(g) | Didion DSL pressure rating for a selected configuration, gas/liquid loads, and droplet removal need confirmation. |
| Separator temperature XMEAS(11) | 79.90 °C | 79.62–80.21 °C | Specify mechanical and material temperature compatibility. |
| Separator underflow XMEAS(14) | 25.15 m³/h | 21.99–27.96 m³/h | One liquid outlet signal; not sufficient to size the entire gas–liquid separator. |
| Recycle flow XMEAS(5) | 26.89 kscmh | 26.33–27.64 kscmh | Compressor sizing also requires actual inlet volumetric flow, gas composition, suction/discharge pressures and compressor map. |
| Compressor work XMEAS(20) | 342.62 kW | 341.56–343.56 kW | Simulated compressor work is **not** a selected electric motor nameplate rating; check efficiency, margins and shaft/drive definition. |
| Stripper pressure XMEAS(16) | 3103.72 kPa(g) / 31.04 bar(g) | 3099.95–3108.58 kPa(g) / 31.00–31.09 bar(g) | **High-priority design gate** for Sulzer engineered column shell, flanges, internals and associated auxiliaries. No pressure-rated model has been verified. |
| Stripper temperature XMEAS(18) | 65.91 °C | 65.79–66.06 °C | Require process composition and thermal/material design. |
| Stripper steam flow XMEAS(19) | 238.19 kg/h | 233.18–242.75 kg/h | Need feed composition, vapor/liquid balance and separation duty before column sizing. |
| Condenser cooling-water valve XMV(11) | 18.24 model control units | 14.37–22.36 | **Cannot infer condenser heat duty** from manipulated valve signal; Alfa Laval Olmi remains pending thermal/mechanical datasheet. |
| Agitator speed manipulation XMV(12) | 50 model control units | 50–50 | This is a manipulated model signal, **not verified RPM, shaft torque or motor power**; EKATO HWL-N and ABB AMZ remain unselected. |

### Engineering disposition

1. **Reactor: standard BE rejected for this observed pressure.** De Dietrich's [official BE family page](https://www.dedietrich.com/en/equipment/process/reaction-agitation/glass-lined-reactors) states a standard −1/+6 bar design pressure and notes customization is possible. Do not represent an unverified customized BE as pressure compliant. Request an independently documented higher-pressure reactor configuration and certified design data.
2. **Stripper: highest observed pressure among the listed vessels.** Sulzer [offers engineered stripping equipment](https://www.sulzer.com/en/shared/products/stripping), but its general offering page does not establish the required pressure rating for a specific column. Obtain a 31+ bar(g) service design proposal, with design margin determined by an engineer.
3. **Separator: pressure rating remains unknown.** Request a certified mechanical rating appropriate for the observed ~26.4 bar(g), and process performance evidence at the relevant phase load.
4. **Condenser/compressor: hold for duty definition.** Valve command and compressor-work readings are insufficient for complete heat-exchanger or compressor selection.
5. **Agitator/motors: hold for mechanical drive definition.** Neither XMV(12)=50 nor compressor work proves synchronous-motor suitability.
6. **No promotion to ProductCatalog, no installed-asset linkage and no equipment approval** until technical review and official configuration-specific datasheets are available.

### Evidence quality and next requests

The observed minima and maxima represent only the selected **fault-free simulation window**; they are **not design extrema**. The summary file lacks sample timestamps, variance, trends, disturbances, physical vessel capacities, full stream compositions and design safety margins. Obtain the underlying wide CSV or Parquet recording, establish steady-state criteria, verify signal units against the simulator, and define an engineering design basis including transient/fault conditions before requesting quotes or approving a configuration.
