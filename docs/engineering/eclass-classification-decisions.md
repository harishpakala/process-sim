# TEP NEXUS — ECLASS classification decision register

**Status:** Historical engineering selections (October 2026), **not** proof of current ProductCatalog implementation, ECLASS release verification, or physical installation. The Tennessee Eastman simulation does not specify commercial equipment.

## Equipment classification decisions

| Physical equipment / asset | ECLASS class | Preferred name | ECLASS class IRDI | Decision / qualification |
|---|---|---|---|---|
| Process control valves (11 physical valves) | 37-01-02-03 | Control globe valve | `0173-1#01-AAD651#023` | Selected; explicitly assumes globe-valve construction |
| Temperature sensors | 27-27-51 | Temperature sensor | `0173-1#01-AHB186#005` | Selected; electrical temperature sensor assumed |
| Pressure sensors | 27-27-49 | Pressure sensor | `0173-1#01-AHB184#005` | Selected |
| Level transmitters | 27-20-05 | Level gauge or transmitter | `0173-1#01-AAC020#014` | Selected; transmitter implementation assumed |
| Reactor | 36-02-01 | Reactor | `0173-1#01-AAD319#012` | Selected |
| Process pumps | 36-41 | Pump | `0173-1#01-AAD563#010` | Selected; not applicable to compressor |
| Condenser | 36-04 | Heat exchanger | `0173-1#01-AAD338#010` | Selected broad class |
| Gas–liquid separator | 36-20-17-04 | Vessel separator (for gases) | `0173-1#01-AKL760#020` | Selected; assumes a vessel-type gas–liquid separator, without specifying internals |
| Stripper | 36-01-01 | Column | `0173-1#01-AAD304#013` | Selected broad industrial column class |
| Reactor agitator assembly | 36-09-08-01 | Agitator (complete) | `0173-1#01-AKP267#021` | Selected; assembly may include motor unless motor is modeled separately |
| Separately modeled pump, compressor, and agitator drive motors | 27-02-24 | Synchronous motor | `0173-1#01-AKE158#012` | Selected as an explicit motor-technology assumption |
| Recycle gas compressor | 36-43 | Compressor, ventilator, vacuum pump | `0173-1#01-AAD585#011` | Selected broad parent class; verify product-class assignability in the ECLASS version in use |

## Representative product selections

| Manufacturer | Selected product / function | ECLASS class | Preferred name | ECLASS class IRDI | Qualification |
|---|---|---|---|---|---|
| SMC | **PFMV505-1** — minute-flow sensor | 27-27-48 | Flow sensor | `0173-1#01-AHB183#005` | Selected; verify process medium and measurement range for any installed location |
| IFM | **LW2720** — non-contact 80 GHz radar level sensor | 27-20-05-05 | Free-space radar level transmitter/switch | `0173-1#01-AAC024#022` | Selected; radar-specific class supersedes the provisional generic level-transmitter class |
| Schneider Electric | **A9MEM3555** — three-phase electricity meter | 27-14-23-16 | Electronic electricity meter | `0173-1#01-AFZ828#022` | Selected; measures an AC electrical circuit, not the modeled 24 V DC instrument bus |
| SAMSON | **Type 3241-7** — pneumatic globe control valve, DN25, Kvs 10 m³/h, PN40 | 37-01-02-03 | Control globe valve | `0173-1#01-AAD651#023` | Selected representative assembly: Type 3277 actuator, Type 3730-1 4–20 mA positioner, normally closed; requires instrument air |
| SMC | **PSE550** — low differential-pressure sensor | 27-20-06-23 | Pressure differential sensor | `0173-1#01-AKA491#001` | Selected; low differential-pressure gas measurement, not automatically suitable for high-pressure TEP streams |
| Phoenix Contact | **2938581** / QUINT-PS-100-240AC/24DC/5 — industrial power supply | 27-04-07-04 | AC-DC supply | `0173-1#01-AFX043#011` | Selected; 24 V DC, 5 A nominal output; check total connected load |
| IFM | **TA1101** — integrated temperature sensor/transmitter | 27-27-51 | Temperature sensor | `0173-1#01-AHB186#005` | Selected instead of the previously considered passive Pt100 TM4101; verify exact signal-interface details against its datasheet |

## Product identity and selection history

| Item | Decision / provenance | Verification boundary |
| --- | --- | --- |
| SAMSON Type 3241-7 / 3730-1 | Tetra Pak catalog number `90533-1149` (supplier reference, **not** verified SAMSON order number); DN25, Kvs 10 m³/h, PN40, Type 3277 actuator, 4–20 mA positioner, normally closed, air-reducing station | Housing described as GS-C25 in detailed data despite “SS/SS” heading; do not infer stainless steel; verify manufacturer identity and instrument-air requirements |
| SMC PSH-L2-01-W | Excluded humidity/condensation checker | Removed from intended ProductCatalog scope |
| Rittal 3244100 | Excluded enclosure filter fan | Do not reuse prior ECAD fan reference as a motor; reconcile ECAD |
| Siemens S55264-V193 | Superseded HVAC valve | Replaced by representative SAMSON 3241-7 selection |
| IFM TM4101 | Superseded passive Pt100 sensor | Replaced by IFM TA1101; verify signal interface |
| IFM LW2720 | Earlier generic class `27-20-05-18` / `0173-1#01-AAC030#023` superseded | Prefer radar-specific `27-20-05-05`; float-switch `27-27-31-05` inapplicable |

## Classification and evidence constraints

| Topic | Boundary / action |
| --- | --- |
| Source of truth | ProductCatalog AAS holds product-type ECLASS information; AssetInventory references products for modeled assets. Inventory coverage is not assumed complete. |
| ECLASS identifiers | IRDIs identify classes, not arbitrary AAS properties. Verify classification against the applicable ECLASS release and whether broad parent classes are assignable. |
| Physical-equipment assumptions | Globe valves, synchronous motors, vessel separator, and broad compressor class are TEP NEXUS modeling choices, not specified TEP benchmark hardware. |
| Mechanical and electrical scope | Model drives separately only when separate assets; 24 V DC instrumentation power does not establish motor drive suitability. |
| Signal distinction | XMEAS/XMV are process signal identifiers, not ECLASS equipment types; XMV(12) controls agitator speed, not a twelfth physical valve. |
| Semantic assurance | A classification or reference in AAS is a declaration, not independent SELiRA validation, verified product fitness, or installed-hardware evidence. |
| Implementation reconciliation | Compare this historical register with current `examples/aas/product_catalog_instance.json` and `examples/aas/asset_inventory_instance.json`; check supplier/manufacturer identifiers, DEXPI/ECAD references, signal/medium suitability, SHACL/RDF lifting, and classification coverage. |
| Next review | Validate AAS templates, ECLASS class assignability, and asset-to-product references before publishing reconciled classifications as authoritative. |
