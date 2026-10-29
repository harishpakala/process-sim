# TEP NEXUS — ECLASS classification decisions (historical working register)

> **Status:** Archived from the project README during documentation cleanup. This is a historical engineering decision register, **not** a live ProductCatalog export or evidence that the listed classifications are currently implemented, verified, or physically installed. Reconcile entries with `examples/aas/product_catalog_instance.json` and `examples/aas/asset_inventory_instance.json` before relying on them.

## TEP NEXUS — ECLASS equipment classification reference (October 2026)

This is the **working classification register** for physical equipment in the Tennessee Eastman Process (TEP) semantic digital twin. The ECLASS names and IRDIs below were supplied from ECLASS lookup during engineering review. They describe **physical product/asset types**, not XMEAS measurements or XMV manipulated-variable identifiers. These selections are design decisions for TEP NEXUS, **not claims that the original TEP simulation specifies particular commercial hardware**.

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

### ProductCatalog — selected commercial products (engineering decision, October 2026)

The following **seven existing commercial product entries** are present in the TEP NEXUS ProductCatalog. ECLASS class names and IRDIs were supplied during engineering review; the classifications are documented here **before** changes to the AAS JSON, ECAD references, or AssetInventory. These are representative commercial products, not hardware specified by the original Tennessee Eastman benchmark.

| Manufacturer | Selected product / function | ECLASS class | Preferred name | ECLASS class IRDI | Qualification |
|---|---|---|---|---|---|
| SMC | **PFMV505-1** — minute-flow sensor | 27-27-48 | Flow sensor | `0173-1#01-AHB183#005` | Selected; verify process medium and measurement range for any installed location |
| IFM | **LW2720** — non-contact 80 GHz radar level sensor | 27-20-05-05 | Free-space radar level transmitter/switch | `0173-1#01-AAC024#022` | Selected; radar-specific class supersedes the provisional generic level-transmitter class |
| Schneider Electric | **A9MEM3555** — three-phase electricity meter | 27-14-23-16 | Electronic electricity meter | `0173-1#01-AFZ828#022` | Selected; measures an AC electrical circuit, not the modeled 24 V DC instrument bus |
| SAMSON | **Type 3241-7** — pneumatic globe control valve, DN25, Kvs 10 m³/h, PN40 | 37-01-02-03 | Control globe valve | `0173-1#01-AAD651#023` | Selected representative assembly: Type 3277 actuator, Type 3730-1 4–20 mA positioner, normally closed; requires instrument air |
| SMC | **PSE550** — low differential-pressure sensor | 27-20-06-23 | Pressure differential sensor | `0173-1#01-AKA491#001` | Selected; low differential-pressure gas measurement, not automatically suitable for high-pressure TEP streams |
| Phoenix Contact | **2938581** / QUINT-PS-100-240AC/24DC/5 — industrial power supply | 27-04-07-04 | AC-DC supply | `0173-1#01-AFX043#011` | Selected; 24 V DC, 5 A nominal output; check total connected load |
| IFM | **TA1101** — integrated temperature sensor/transmitter | 27-27-51 | Temperature sensor | `0173-1#01-AHB186#005` | Selected instead of the previously considered passive Pt100 TM4101; verify exact signal-interface details against its datasheet |

**SAMSON part-number provenance:** Tetra Pak's Plant Components catalog lists **`90533-1149`** for the **3241-7 / 3730-1, DN25, Kvs 10.00 m³/h** assembly. This is a **Tetra Pak supplier/catalog part number**, **not a verified SAMSON manufacturer order number**. Keep supplier and manufacturer identifiers separate in the future ProductCatalog AAS. The supplied listing also specifies DIN PN40 flanges, cast-steel GS-C25 housing, Type 3277 pneumatic actuator, Type 3730-1 positioner (4–20 mA), normally closed operation, and an included air-reducing station. Its heading says “SS/SS,” while the detailed housing field says GS-C25; do not silently infer a stainless-steel housing.

**Explicit exclusions and replacements:**

- **SMC PSH-L2-01-W** humidity/condensation checker — removed from the intended ProductCatalog scope.
- **Rittal 3244100** enclosure filter fan — removed from the intended ProductCatalog scope; existing ECAD motor-device references to this fan part number require correction, not reuse as a motor.
- **Siemens S55264-V193** HVAC pressure-independent valve — superseded by the selected **SAMSON Type 3241-7** representative process-control valve.
- **IFM TM4101** passive Pt100 temperature sensor — considered but superseded by **IFM TA1101**.
- The earlier generic **LW2720** candidate `27-20-05-18` / `0173-1#01-AAC030#023` is superseded by the radar-specific `27-20-05-05` class. Float-switch classification `27-27-31-05` is inapplicable.

**Implementation status:** This section records **agreed selections only**. The source `examples/aas/product_catalog_instance.json` still reflects the prior eight-product snapshot until a separate implementation commit; the seven-product selection has **not** yet been written into that AAS instance. The earlier counts and cross-domain part-number match statistics in this README refer to the existing snapshot and must be recalculated after changes. Validate manufacturer/supplier identity, electrical/pneumatic connections, DEXPI/ECAD/AssetInventory references, ECLASS release compatibility, and SHACL/RDF lifting after implementation.

### Classification rules and evidence boundaries

- **ProductCatalog AAS** should hold the authoritative ECLASS classification for a product type; **AssetInventory AAS** should reference that product for each installed asset. Validate actual inventory coverage before claiming every physical asset is classified.
- Each `0173-1#01-...#...` identifier above is an **ECLASS class IRDI**. Do not reuse it as the semantic ID of an unrelated AAS property such as `DeviceType`.
- Classify the **driven machine** and its **electric motor** separately only where the motor is represented as a distinct asset. The agitator's *complete* assembly classification must not be confused with the standalone motor classification.
- The recycle compressor's broad 36-43 class avoids an unsupported assumption about rotary positive displacement, reciprocating compression, or turbo compression. **Confirm whether the parent class is directly assignable** in the selected ECLASS release before implementing the ProductCatalog mapping.
- The gas–liquid separator selection assumes a **vessel separator**. The TEP process model does not specify separator internals.
- The eleven globe-valve selections and the synchronous-motor selection are **TEP NEXUS modeling assumptions** rather than verified original TEP equipment specifications. XMV(12) denotes agitator speed control, **not a twelfth physical control valve**.
- Synchronous motors require appropriate electrical drive arrangements. A 24 V DC instrumentation supply does **not** by itself establish suitable motor power or drive compatibility. ECAD power distribution and motor-drive details remain a separate consistency review.
- ProductCatalog AAS entries include ECLASS class and IRDI values; the working equipment classifications still require ECLASS release/assignability verification. AssetInventory classification coverage must be checked separately.

### Reviewed alternatives not selected

- **Linear DC motor** (`0173-1#01-ADJ119#015`) and **Linear induction motor** (`0173-1#01-ADJ117#015`): linear rather than rotary motion.
- **Universal motor** (`0173-1#01-AKE157#019`): rotary, but not the selected continuous industrial-drive technology.
- **Electric motor (motor vehicle)** (`0173-1#01-AFX525#006`) and **Motor (hydraulics, other)** (`0173-1#01-AGU935#004`): incorrect application domain or energy-conversion technology.
- **Submersible motor pump** (`0173-1#01-AKL848#022`): assumes submerged pump construction and describes a pump unit rather than a standalone drive motor.
- **Compressor (positive type, rotating)** (`0173-1#01-AAD586#013`), **Compressor (special execution)** (`0173-1#01-AAD589#012`), and **Compressor, ventilator, vacuum pump (other)** (`0173-1#01-AKL925#012`): not selected without evidence of the specified design or an actual *other* subtype.

**Next implementation step:** validate the updated ProductCatalog JSON against the AAS template and SHACL shapes, verify ECLASS class assignability, then reconcile product/asset references before any RDF publication or AssetInventory linking. Keep ECAD electrical topology changes separate from this documentation step.
