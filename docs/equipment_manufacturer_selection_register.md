# TEP NEXUS — manufacturer-backed equipment candidate register

Status: **research shortlist, not an approved equipment selection**. Updated 2026-10-21.

The Tennessee Eastman Process (TEP) is a simulation benchmark, not a procurement design package. These seven entries are **manufacturer-backed product families or engineered offerings**, not confirmed installed products. ECLASS class/IRDI values are inherited from the project's README working classification register; **they have not been independently checked against the official ECLASS release**. No manufacturer part number, equipment rating, asset tag, or purchase claim is inferred.

| TEP equipment | ECLASS class | ECLASS IRDI | Manufacturer / candidate | Evidence and verified manufacturer-family facts | Selection status | Engineering information still required |
|---|---|---|---|---|---|---|
| Reactor | 36-02-01 | `0173-1#01-AAD319#012` | De Dietrich — BE glass-lined reactor family (previous shortlist; **official product source still to be independently verified**) | Manufacturer and model-family claim retained only as a **lead**, not validated by the sources checked for this register | **Source verification pending** | Vessel volume, design/operating pressure, temperature, heat-transfer duty, reactants/material compatibility, agitator interface, official model datasheet |
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

- [ ] Obtain a citable official manufacturer reactor page and confirm the exact De Dietrich family designation.
- [ ] Extract process requirements for each equipment item from the TEP model and mark unavailable inputs as explicit engineering assumptions.
- [ ] Verify condenser duty and separator phase-loading applicability.
- [ ] Confirm compressor type, process gas compatibility and ECLASS class assignability.
- [x] Identify a **complete stripping-column offering** (Sulzer).
- [ ] Confirm agitator and motor equipment boundaries and individual drive powers.
- [ ] Check ECLASS mappings against the project's selected official ECLASS release.
- [ ] Review/approve candidate selections before writing ProductCatalog AAS entries, linking assets, lifting RDF and publishing to GraphDB.

## Evidence policy

Links above are primary manufacturer sources. A manufacturer-family capability is evidence that an offering exists, **not evidence of suitability** for the benchmark. Candidate selections can change as design requirements become available.
